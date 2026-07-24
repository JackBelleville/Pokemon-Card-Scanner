import sqlite3
import os
import cardSet
import pokedex
import evolutionsSet
import imagehash
import numpy as np

databasename = "pokemonDatabase.db"  # File the SQLite database is stored in


# Creates a database of pokemon
def createDatabase():
    # Remove any existing database file so we always start from a clean slate
    # (in case the user forgot to set isFirst back to False after already creating it)
    if os.path.exists(databasename):
        os.remove(databasename)

    # Add tables and values to database
    initializeDatabase()


# Initializes database with inital values for cards and pokemon
def initializeDatabase():
    # Connects to the database file, creating it if it does not yet exist
    db = sqlite3.connect(databasename)

    # Creates a cursor so that we can edit the database
    mycursor = db.cursor()

    # Creates a Pokedex object that holds information on the first 151 (Kanto) Pokemon and some of their mega evolutions
    # Information includes pokedex number, pokemon names, type, stage, and height
    poke = pokedex.Pokedex()

    # Creates a CardSet object that has information on the cards in Evolutions
    # Information includes card numbers, pokemon names, card names, card rarity, and card type
    evoSet = cardSet.CardSet()

    # Creates a EvolutionsSet object that stores the hashes for the images of the Pokemon cards
    # Has hashes for the following orientations of the card: normal, mirrored, upside-down, upside down mirrored
    evoCards = evolutionsSet.EvolutionsSet()

    # Creates a new table Pokemon that will hold the values in the poke Pokedex object
    mycursor.execute("CREATE TABLE Pokemon (dexNumber INTEGER, pokemon TEXT PRIMARY KEY, \
            poketype TEXT, height REAL, stage TEXT)")

    # Populates the Pokemon table
    for x in range(poke.numpoke):
        mycursor.execute("INSERT INTO Pokemon (dexNumber, pokemon, poketype, stage, height) VALUES(?, ?, ?, ?, ?)",
                         (poke.dexnumber[x], poke.pokemon[x], poke.type[x], poke.stage[x], poke.height[x]))

    # Creates a new table EvolutionsSet that will hold the values in the evoSet CardSet object
    mycursor.execute("CREATE TABLE EvolutionsSet (cardnumber INTEGER PRIMARY KEY AUTOINCREMENT, \
            cardname TEXT, pokemon TEXT, rarity TEXT, cardtype TEXT)")

    # Populates the EvolutionsSet table
    for x in range(evoSet.numCards):
        mycursor.execute("INSERT INTO EvolutionsSet (cardname, pokemon, rarity, cardtype) VALUES(?, ?, ?, ?)",
                         (evoSet.cardnamelist[x], evoSet.pokemonlist[x], evoSet.rarity[x], evoSet.cardtype[x]))

    # Creates a new table EvolutionsCards that will hold the values in the evoCards EvolutionsSet object
    mycursor.execute("CREATE TABLE EvolutionsCards (cardnumber INTEGER PRIMARY KEY AUTOINCREMENT, \
            avghashes TEXT, avghashesmir TEXT, avghashesud TEXT, avghashesudmir TEXT, \
            whashes TEXT, whashesmir TEXT, whashesud TEXT, whashesudmir TEXT, \
            phashes TEXT, phashesmir TEXT, phashesud TEXT, phashesudmir TEXT, \
            dhashes TEXT, dhashesmir TEXT, dhashesud TEXT, dhashesudmir TEXT, \
            FOREIGN KEY(cardnumber) REFERENCES EvolutionsSet(cardnumber))")

    # Populates the EvolutionsCards table
    for x in range(evoCards.setSize):
        mycursor.execute(
            "INSERT INTO EvolutionsCards (avghashes, avghashesmir, avghashesud, avghashesudmir, \
            whashes, whashesmir, whashesud, whashesudmir, \
            phashes, phashesmir, phashesud, phashesudmir, \
            dhashes, dhashesmir, dhashesud, dhashesudmir) \
            VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (evoCards.hashes[x][0], evoCards.hashesmir[x][0], evoCards.hashesud[x][0], evoCards.hashesudmir[x][0],
             evoCards.hashes[x][1], evoCards.hashesmir[x][1], evoCards.hashesud[x][1], evoCards.hashesudmir[x][1],
             evoCards.hashes[x][2], evoCards.hashesmir[x][2], evoCards.hashesud[x][2], evoCards.hashesudmir[x][2],
             evoCards.hashes[x][3], evoCards.hashesmir[x][3], evoCards.hashesud[x][3], evoCards.hashesudmir[x][3]))

    # Commits changes to the database
    db.commit()
    db.close()


# Returns a dictionary of values of the matching Pokemon card if the hash distance is within the cutoff range
# If no matching card is found, it returns None
def compareCards(hashes):
    cutoff = 18  # Arbitrarily set cutoff value; was found through testing
    # Connects to the pokemon card database
    db = sqlite3.connect(databasename)

    mycursor = db.cursor()

    mycursor.execute("SELECT * FROM EvolutionsCards")  # Gets values from EvolutionsCards (hashes)
    rows = mycursor.fetchall()  # SQLite does not populate rowcount, so fetch every row up front

    # Create arrays of size=4 that store hash differences for each orientation; every hashing method gets its own array
    avghashesDists = np.zeros(4)
    whashesDists = np.zeros(4)
    phashesDists = np.zeros(4)
    dhashesDists = np.zeros(4)

    maxHashDists = []  # An array that will store the maximum of the minimum hash difference for each card

    for row in rows:  # Loop through each row in EvolutionsCards table
        # Get the values stored in each row
        # Note: the hashes are stored as Strings in the database because SQL doesn't support storing hashes
        cardnum, \
            avghash1, avghash2, avghash3, avghash4, \
            whash1, whash2, whash3, whash4,\
            phash1, phash2, phash3, phash4, \
            dhash1, dhash2, dhash3, dhash4 = row

        # Convert each hash from a String to a hash and find the distance from the scanned image
        avghashesDists[0] = hashes[0] - imagehash.hex_to_hash(avghash1)
        avghashesDists[1] = hashes[0] - imagehash.hex_to_hash(avghash2)
        avghashesDists[2] = hashes[0] - imagehash.hex_to_hash(avghash3)
        avghashesDists[3] = hashes[0] - imagehash.hex_to_hash(avghash4)

        whashesDists[0] = hashes[1] - imagehash.hex_to_hash(whash1)
        whashesDists[1] = hashes[1] - imagehash.hex_to_hash(whash2)
        whashesDists[2] = hashes[1] - imagehash.hex_to_hash(whash3)
        whashesDists[3] = hashes[1] - imagehash.hex_to_hash(whash4)

        phashesDists[0] = hashes[2] - imagehash.hex_to_hash(phash1)
        phashesDists[1] = hashes[2] - imagehash.hex_to_hash(phash2)
        phashesDists[2] = hashes[2] - imagehash.hex_to_hash(phash3)
        phashesDists[3] = hashes[2] - imagehash.hex_to_hash(phash4)

        dhashesDists[0] = hashes[3] - imagehash.hex_to_hash(dhash1)
        dhashesDists[1] = hashes[3] - imagehash.hex_to_hash(dhash2)
        dhashesDists[2] = hashes[3] - imagehash.hex_to_hash(dhash3)
        dhashesDists[3] = hashes[3] - imagehash.hex_to_hash(dhash4)

        # Find the minimum of each hashing method
        # This should make us look at the correct card orientation
        hashDistances = [min(avghashesDists), min(whashesDists), min(phashesDists), min(dhashesDists)]
        maxHashDists.append(max(hashDistances))  # Find the max of the mins of each hashing method to reduce error

    print(min(maxHashDists))
    if min(maxHashDists) < cutoff:  # If the smallest hash distance is less than the cutoff, we have found our card
        minCardNum = maxHashDists.index(min(maxHashDists)) + 1  # Find the card number of the card

        # Get values from minCardNum row of EvolutionsSet table
        mycursor.execute("SELECT * FROM EvolutionsSet WHERE cardnumber=?", (minCardNum,))
        vals = mycursor.fetchone()
        _, cardname, poke, rarity, cardtype = vals

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
        return {'Card Number': minCardNum,
                'Pokemon': poke,
                'Card Name': cardname,
                'Rarity': rarity,
                'Card Type': cardtype,
                'Pokedex Number': dexnumber,
                'Pokemon Type': poketype,
                'Pokemon Stage': stage,
                'Pokemon Height': height}
    db.close()
    return None
