# Discovery and loading of card sets.
#
# A set is a folder under sets/ and needs no code changes to be added:
#
#   sets/<setid>/set.json    metadata (see CardSetDef.load for the fields)
#   sets/<setid>/cards.csv   one row per card: cardnumber,cardname,pokemon,rarity,cardtype
#   sets/<setid>/images/     one image per card, named after the padded card number
#
# See README.md for a walkthrough of adding a set.
import collections
import csv
import json
import os

import numpy as np
import imagehash
from PIL import Image, ImageOps

SETSDIR = 'sets'  # Folder every set lives in, relative to the project root

# Loading a set means reading a file off disk, but compareCards() needs the set on every
# frame of a live feed, so completed loads are kept here and handed back on later calls
_loadedSets = {}


# A single card set: its metadata plus the card list read from cards.csv
class CardSetDef:
    def __init__(self, setid, meta, cards):
        self.setid = setid
        self.meta = meta
        self.cards = cards  # List of dicts with keys cardnumber, cardname, pokemon, rarity, cardtype

        self.name = meta.get('name', setid)  # Human-readable set name, e.g. 'Evolutions'
        self.imageExt = meta.get('imageExt', '.png')  # File extension of the card images
        self.padding = int(meta.get('padding', 3))  # Zero-padding of image filenames; 3 gives 001.png
        # Hash distance below which a scan counts as a match. Tuned per set because sets
        # with more cards, or with art reused from an earlier set, need a tighter value
        self.cutoff = float(meta.get('cutoff', 18))
        self.numCards = len(cards)

    # Path to the folder holding this set's files
    def dir(self):
        return os.path.join(SETSDIR, self.setid)

    # Path to the image of a single card, e.g. sets/evolutions/images/001.png
    def imagePath(self, cardnumber):
        filename = str(cardnumber).rjust(self.padding, '0') + self.imageExt
        return os.path.join(self.dir(), 'images', filename)

    # Reads set.json and cards.csv from sets/<setid>/ and returns a CardSetDef
    @staticmethod
    def load(setid):
        setdir = os.path.join(SETSDIR, setid)
        metapath = os.path.join(setdir, 'set.json')
        cardspath = os.path.join(setdir, 'cards.csv')

        if not os.path.isfile(metapath):
            raise FileNotFoundError(f"Set '{setid}' has no set.json (looked in {setdir})")
        if not os.path.isfile(cardspath):
            raise FileNotFoundError(f"Set '{setid}' has no cards.csv (looked in {setdir})")

        with open(metapath, encoding='utf-8') as f:
            meta = json.load(f)

        cards = []
        with open(cardspath, newline='', encoding='utf-8') as f:
            for lineno, row in enumerate(csv.DictReader(f), start=2):  # Line 1 is the header
                missing = [c for c in ('cardnumber', 'cardname', 'pokemon', 'rarity', 'cardtype')
                           if row.get(c) is None]
                if missing:
                    raise ValueError(f'{cardspath} line {lineno}: missing column(s) {", ".join(missing)}')
                try:
                    number = int(row['cardnumber'])
                except ValueError:
                    raise ValueError(f"{cardspath} line {lineno}: cardnumber '{row['cardnumber']}' is not a number")
                cards.append({'cardnumber': number,
                              'cardname': row['cardname'],
                              'pokemon': row['pokemon'],
                              'rarity': row['rarity'],
                              'cardtype': row['cardtype']})

        if not cards:
            raise ValueError(f'{cardspath} lists no cards')

        counts = collections.Counter(c['cardnumber'] for c in cards)
        duplicates = sorted(number for number, count in counts.items() if count > 1)
        if duplicates:
            raise ValueError(f'{cardspath} repeats card number(s): {duplicates}')

        return CardSetDef(setid, meta, cards)


# Returns the ids of every set found under sets/, sorted alphabetically
def listSetIds():
    if not os.path.isdir(SETSDIR):
        return []
    ids = []
    for entry in sorted(os.listdir(SETSDIR)):
        if os.path.isfile(os.path.join(SETSDIR, entry, 'set.json')):
            ids.append(entry)
    return ids


# Returns a loaded CardSetDef for every set found under sets/
# Sets that fail to load are skipped so one bad folder cannot hide the rest; the reason is printed
def listSets():
    sets = []
    for setid in listSetIds():
        try:
            sets.append(loadSet(setid))
        except (ValueError, OSError, json.JSONDecodeError) as e:
            print(f"Skipping set '{setid}': {e}")
    return sets


# Returns the CardSetDef for a set id, reading it from disk the first time it is asked for
def loadSet(setid):
    if setid not in _loadedSets:
        _loadedSets[setid] = CardSetDef.load(setid)
    return _loadedSets[setid]


# Returns the card numbers that cards.csv lists but that have no image file
def missingImages(setdef):
    return [c['cardnumber'] for c in setdef.cards if not os.path.isfile(setdef.imagePath(c['cardnumber']))]


# Gets the average hash, whash, phash & dhash of every card in a set in each of four
# orientations, for a total of 16 hashes per card. Four different hashing methods are
# used to reduce the potential for error in relying on only one of them.
# Returns a dict of {orientation: numCards x 4 array of hash strings}, in cards.csv order.
def hashSet(setdef, progress=None):
    absent = missingImages(setdef)
    if absent:
        shown = ', '.join(str(n) for n in absent[:10])
        more = f' (and {len(absent) - 10} more)' if len(absent) > 10 else ''
        raise FileNotFoundError(
            f"Set '{setdef.setid}' is missing images for card number(s) {shown}{more}. "
            f'Expected files like {setdef.imagePath(absent[0])}')

    orientations = ('hash', 'hashmir', 'hashud', 'hashudmir')
    arrays = {o: np.empty((setdef.numCards, 4), dtype=object) for o in orientations}

    for i, card in enumerate(setdef.cards):
        img = Image.open(setdef.imagePath(card['cardnumber']))
        for orientation in orientations:
            match orientation:
                case 'hash':  # Normally oriented card
                    oriented = img
                case 'hashmir':  # Mirrored card
                    oriented = ImageOps.mirror(img)
                case 'hashud':  # Upside down card
                    oriented = ImageOps.flip(img)
                case 'hashudmir':  # Upside down & mirrored card
                    oriented = ImageOps.flip(ImageOps.mirror(img))
            # Find the average hash, whash, phash & dhash of the image & convert each to a string
            arrays[orientation][i][0] = str(imagehash.average_hash(oriented))
            arrays[orientation][i][1] = str(imagehash.whash(oriented))
            arrays[orientation][i][2] = str(imagehash.phash(oriented))
            arrays[orientation][i][3] = str(imagehash.dhash(oriented))
        img.close()

        if progress is not None:
            progress(i + 1, setdef.numCards)

    return arrays
