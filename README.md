Pokémon Card Scanner
=========================


https://user-images.githubusercontent.com/57413019/187007394-c514c680-810f-4ce1-b1dc-e10459b5b45c.mp4


This repository contains Python code for a Pokémon card scanner and identifier. You pick the set you are scanning from and the card is identified from that set's card list. Sets are plain data on disk, so a new one can be added without touching any code — the [Evolutions set](https://bulbapedia.bulbagarden.net/wiki/Evolutions_%28TCG%29) ships with it as an example.

Running it
----------

```
python main.py                      # lists the available sets and asks which one you are scanning from
python main.py --set evolutions     # skip the prompt
python main.py --list-sets          # show what is installed and exit
python main.py --set evolutions --image testImages/tiltright.jpg   # read an image file instead of the webcam
python main.py --set evolutions --camera 1 --rotate                # a phone in portrait via the Iriun Webcam app
python main.py --set evolutions --reindex                          # re-hash a set after changing its files
```

The first time a set is used, its card images are hashed into the database, which takes a moment. Every later run reuses those stored hashes, so only a newly added set pays that cost.

How it works
------------

If live video is chosen, the webcam is used, which can be connected to a smart phone using the `Iriun Webcam` app.

Using the `OpenCV` library, we can get a normalized scan (think PDF scanner apps) of the Pokémon card in the feed by doing the following:
 1. Taking in a single image or video feed
 2. Finding edges in the image/frame
 3. Finding the biggest contour that is a rectangle
 4. Finding the corners of the biggest contour
 5. Identifying which corner is which (i.e. reordering the corners to ensure that they are in the order: topLeft, topRight, bottomLeft, bottomRight)
 6. Creating a transformation matrix based on the original corners to transform the image / frame of the card into a vertical rectangle

It then gets the hashes (average hash, whash, phash, dhash) of the scanned card using the `ImageHash` library and compares these hashes to their counterparts for each card **in the selected set** by finding the distance between these hashes. By using four different hashing methods, we can reduce the margin of error that only using one may introduce. A smaller distance is indicative of cards being more similar. A cutoff value is defined so as if a hash distance is smaller than it, we can assume the images are similar.

Adding a set
------------

A set is a folder under `sets/`. Create three things and it shows up in the menu on the next run:

```
sets/
  yoursetid/
    set.json     metadata
    cards.csv    one row per card
    images/      one image per card, named after the padded card number
```

**`set.json`** — `id` must match the folder name:

```json
{
  "id": "evolutions",
  "name": "Evolutions",
  "series": "XY",
  "imageExt": ".png",
  "padding": 3,
  "cutoff": 18
}
```

| field | meaning |
|--|--|
| `id` | Folder name, and what you pass to `--set` |
| `name` | Name shown in the menu and on the card info window |
| `imageExt` | Extension of the card images, e.g. `.png` or `.jpg` |
| `padding` | Zero-padding of the image filenames; `3` means card 1 is `001.png` |
| `cutoff` | Hash distance below which a scan counts as a match (see the note below) |

**`cards.csv`** — a header row followed by one row per card. Card numbers do not have to be contiguous, so secret rares numbered past the set size are fine:

```csv
cardnumber,cardname,pokemon,rarity,cardtype
1,Venusaur EX,Venusaur,EX Rare,Pokemon
2,M Venusaur EX,Mega Venusaur,EX Rare,Pokemon
3,Caterpie,Caterpie,Common,Pokemon
```

`pokemon` is used to look up extra details in the shared `Pokemon` table. Use `NA` for trainer and energy cards. Any Pokémon outside the Kanto pokedex simply shows `N/A` for the pokedex fields rather than failing.

**`images/`** — one image per card number listed in `cards.csv`, named with the padding from `set.json` (`001.png`, `002.png`, …). If any are missing, the set reports exactly which card numbers before writing anything to the database.

*Tuning `cutoff`:* the value of 18 was found by testing against Evolutions' 113 cards. Sets that are larger, or that reuse artwork from an earlier set, may need a lower value to avoid false matches. Scan a few known cards with `--image` and watch the printed hash distance: correct matches on the sample images sit around 8-10, while non-matches sit at 20 and up.

Database
--------

Everything lives in the `pokemonDatabase.db` SQLite file, in four tables shared by every set. Adding a set inserts rows; it never adds tables.

**Sets**:
| setid | name | numcards |
|--|--|--|

**Cards**:
| setid | cardnumber | cardname | pokemon | rarity | cardtype |
|--|--|--|--|--|--|

**CardHashes**:
| setid | cardnumber | avghashes | avghashesmir | avghashesud | avghashesudmir | whashes | whashesmir | whashesud | whashesudmir | phashes | phashesmir | phashesud | phashesudmir | dhashes | dhashesmir | dhashesud | dhashesudmir |
|--|--|--|--|--|--|--|--|--|--|--|--|--|--|--|--|--|--|

**Pokémon** (shared by all sets; the first 151 Kanto Pokémon and some mega evolutions):
| dexnumber | pokemon | type | stage | height |
|--|--|--|--|--|

*Note: The **CardHashes** table has four hashes saved for each hashing method, representing different orientations the card may be in (normal, mirrored, upside down, mirrored & upside down) to ensure that a card can be scanned no matter its orientation.*

If a similar card is found, information on said card is printed to the console and shown in a card info window. If the code was using a live feed, it is aborted.

Files
-----

| file | role |
|--|--|
| `main.py` | Set selection and the scan loop |
| `cardSets.py` | Finds sets under `sets/`, reads their `set.json` / `cards.csv`, hashes their images |
| `cardData.py` | The SQLite database: schema, per-set indexing, and hash comparison |
| `utils.py` | Contour finding, perspective correction, and the display windows |
| `pokedex.py` | The shared Kanto pokedex data |
| `test_headless.py` | Runs the pipeline over `testImages/` with no windows: `python test_headless.py [setid]` |
