import sqlite3
import os
import cardSets
import pokedex
import imagehash
import numpy as np

databasename = "pokemonDatabase.db"  # File the SQLite database is stored in

# Parsing the 16 hex hashes of every card out of the database on every frame of a live feed
# is wasted work, so each set's parsed hashes are kept here after the first comparison
_hashCache = {}


# Opens the database, creating the tables if this is the first run
def connect():
    db = sqlite3.connect(databasename)
    createTables(db)
    return db


# Creates the tables if they do not exist yet. All three are shared by every set:
# adding a set inserts rows, it does not add tables.
def createTables(db):
    mycursor = db.cursor()

    # One row per set that has been indexed into the database
    mycursor.execute("CREATE TABLE IF NOT EXISTS Sets (setid TEXT PRIMARY KEY, name TEXT, numcards INTEGER)")

    # The card list of every set, straight from each set's cards.csv
    mycursor.execute("CREATE TABLE IF NOT EXISTS Cards (setid TEXT, cardnumber INTEGER, \
            cardname TEXT, pokemon TEXT, rarity TEXT, cardtype TEXT, \
            PRIMARY KEY (setid, cardnumber), FOREIGN KEY(setid) REFERENCES Sets(setid))")

    # The 16 image hashes of every card: four hashing methods in four orientations
    mycursor.execute("CREATE TABLE IF NOT EXISTS CardHashes (setid TEXT, cardnumber INTEGER, \
            avghashes TEXT, avghashesmir TEXT, avghashesud TEXT, avghashesudmir TEXT, \
            whashes TEXT, whashesmir TEXT, whashesud TEXT, whashesudmir TEXT, \
            phashes TEXT, phashesmir TEXT, phashesud TEXT, phashesudmir TEXT, \
            dhashes TEXT, dhashesmir TEXT, dhashesud TEXT, dhashesudmir TEXT, \
            PRIMARY KEY (setid, cardnumber), \
            FOREIGN KEY(setid, cardnumber) REFERENCES Cards(setid, cardnumber))")

    # Information on the first 151 (Kanto) Pokemon and some of their mega evolutions.
    # Shared by every set: pokedex number, pokemon names, type, stage, and height
    mycursor.execute("CREATE TABLE IF NOT EXISTS Pokemon (dexNumber INTEGER, pokemon TEXT PRIMARY KEY, \
            poketype TEXT, height REAL, stage TEXT)")

    db.commit()


# Populates the Pokemon table if it is empty
def initializePokedex(db):
    mycursor = db.cursor()
    if mycursor.execute("SELECT COUNT(*) FROM Pokemon").fetchone()[0] > 0:
        return

    poke = pokedex.Pokedex()
    for x in range(poke.numpoke):
        mycursor.execute("INSERT INTO Pokemon (dexNumber, pokemon, poketype, stage, height) VALUES(?, ?, ?, ?, ?)",
                         (poke.dexnumber[x], poke.pokemon[x], poke.type[x], poke.stage[x], poke.height[x]))
    db.commit()


# Returns True if the set has already been hashed into the database
def isSetIndexed(setid):
    db = connect()
    row = db.execute("SELECT numcards FROM Sets WHERE setid=?", (setid,)).fetchone()
    db.close()
    return row is not None


# Makes sure a set is ready to scan against, hashing its card images into the database
# the first time it is used. Later runs reuse the stored hashes, so only a newly added
# set pays the hashing cost. Pass force=True to re-hash a set whose files have changed.
def ensureSetIndexed(setid, force=False):
    setdef = cardSets.loadSet(setid)

    db = connect()
    initializePokedex(db)

    existing = db.execute("SELECT numcards FROM Sets WHERE setid=?", (setid,)).fetchone()
    if existing is not None and not force:
        db.close()
        return setdef

    print(f"Indexing set '{setdef.name}' ({setdef.numCards} cards). This runs once and may take a moment...")

    def progress(done, total):
        if done % 25 == 0 or done == total:
            print(f'  hashed {done}/{total} cards')

    # Hash first: if an image is missing this raises before anything is written,
    # leaving the set unindexed rather than half-indexed
    arrays = cardSets.hashSet(setdef, progress=progress)

    mycursor = db.cursor()
    # Clear any earlier rows so a forced re-index does not leave stale cards behind
    mycursor.execute("DELETE FROM CardHashes WHERE setid=?", (setid,))
    mycursor.execute("DELETE FROM Cards WHERE setid=?", (setid,))
    mycursor.execute("DELETE FROM Sets WHERE setid=?", (setid,))

    mycursor.execute("INSERT INTO Sets (setid, name, numcards) VALUES(?, ?, ?)",
                     (setid, setdef.name, setdef.numCards))

    for x, card in enumerate(setdef.cards):
        mycursor.execute("INSERT INTO Cards (setid, cardnumber, cardname, pokemon, rarity, cardtype) \
                VALUES(?, ?, ?, ?, ?, ?)",
                         (setid, card['cardnumber'], card['cardname'],
                          card['pokemon'], card['rarity'], card['cardtype']))

        mycursor.execute(
            "INSERT INTO CardHashes (setid, cardnumber, \
            avghashes, avghashesmir, avghashesud, avghashesudmir, \
            whashes, whashesmir, whashesud, whashesudmir, \
            phashes, phashesmir, phashesud, phashesudmir, \
            dhashes, dhashesmir, dhashesud, dhashesudmir) \
            VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (setid, card['cardnumber'],
             arrays['hash'][x][0], arrays['hashmir'][x][0], arrays['hashud'][x][0], arrays['hashudmir'][x][0],
             arrays['hash'][x][1], arrays['hashmir'][x][1], arrays['hashud'][x][1], arrays['hashudmir'][x][1],
             arrays['hash'][x][2], arrays['hashmir'][x][2], arrays['hashud'][x][2], arrays['hashudmir'][x][2],
             arrays['hash'][x][3], arrays['hashmir'][x][3], arrays['hashud'][x][3], arrays['hashudmir'][x][3]))

    db.commit()
    db.close()

    _hashCache.pop(setid, None)  # Any cached hashes are now out of date
    print(f"Set '{setdef.name}' is ready.")
    return setdef


# Deletes the database file so the next run rebuilds it from scratch
def createDatabase():
    if os.path.exists(databasename):
        os.remove(databasename)
    _hashCache.clear()
    db = connect()
    initializePokedex(db)
    db.close()


# Reads a set's hashes out of the database and converts them from strings back into hashes
# Note: the hashes are stored as Strings in the database because SQL doesn't support storing hashes
# Returns a list of (cardnumber, 4 methods x 4 orientations array of hashes)
def getSetHashes(setid):
    if setid in _hashCache:
        return _hashCache[setid]

    db = connect()
    rows = db.execute("SELECT * FROM CardHashes WHERE setid=? ORDER BY cardnumber", (setid,)).fetchall()
    db.close()

    parsed = []
    for row in rows:
        # Get the values stored in each row
        _, cardnum, \
            avghash1, avghash2, avghash3, avghash4, \
            whash1, whash2, whash3, whash4, \
            phash1, phash2, phash3, phash4, \
            dhash1, dhash2, dhash3, dhash4 = row

        # Row per hashing method, column per card orientation
        parsed.append((cardnum, [
            [imagehash.hex_to_hash(h) for h in (avghash1, avghash2, avghash3, avghash4)],
            [imagehash.hex_to_hash(h) for h in (whash1, whash2, whash3, whash4)],
            [imagehash.hex_to_hash(h) for h in (phash1, phash2, phash3, phash4)],
            [imagehash.hex_to_hash(h) for h in (dhash1, dhash2, dhash3, dhash4)],
        ]))

    _hashCache[setid] = parsed
    return parsed


# Returns a dictionary of values of the matching Pokemon card in the given set if the hash
# distance is within that set's cutoff range. If no matching card is found, it returns None.
def compareCards(hashes, setid):
    setdef = cardSets.loadSet(setid)
    cutoff = setdef.cutoff  # Set in the set's set.json; found through testing

    cards = getSetHashes(setid)
    if not cards:
        raise LookupError(f"Set '{setid}' has not been indexed yet; call cardData.ensureSetIndexed('{setid}') first")

    maxHashDists = []  # An array that will store the maximum of the minimum hash difference for each card
    cardNumbers = []  # The card number each entry of maxHashDists belongs to

    for cardnum, cardHashes in cards:  # Loop through each card of the set
        # For each hashing method, find the distance from the scanned image in all four orientations
        # and keep the smallest. This should make us look at the correct card orientation.
        hashDistances = [min(hashes[method] - stored for stored in cardHashes[method])
                         for method in range(4)]
        maxHashDists.append(max(hashDistances))  # Find the max of the mins of each hashing method to reduce error
        cardNumbers.append(cardnum)

    bestDist = min(maxHashDists)
    print(bestDist)
    if bestDist >= cutoff:  # Nothing was close enough to call a match
        return None

    minCardNum = cardNumbers[maxHashDists.index(bestDist)]  # Find the card number of the card

    db = connect()
    mycursor = db.cursor()

    # Get the matching card's row from the Cards table
    mycursor.execute("SELECT cardname, pokemon, rarity, cardtype FROM Cards WHERE setid=? AND cardnumber=?",
                     (setid, minCardNum))
    cardname, poke, rarity, cardtype = mycursor.fetchone()

    # Get values from poke row of Pokemon table
    mycursor.execute("SELECT * FROM Pokemon WHERE pokemon=?", (poke,))
    vals2 = mycursor.fetchone()
    db.close()

    # Trainer cards and Pokemon outside the Kanto pokedex have no matching Pokemon row
    if vals2 is None:
        dexnumber = poketype = height = stage = 'N/A'
    else:
        dexnumber, _, poketype, height, stage = vals2

    # Return dictionary with traits about cards
    return {'Set': setdef.name,
            'Set Id': setid,
            'Card Number': minCardNum,
            'Pokemon': poke,
            'Card Name': cardname,
            'Rarity': rarity,
            'Card Type': cardtype,
            'Pokedex Number': dexnumber,
            'Pokemon Type': poketype,
            'Pokemon Stage': stage,
            'Pokemon Height': height}
