# Measures how well the scanner recognises cards, instead of leaving it to be eyeballed.
#
# Two reports:
#   python evaluate.py          run every fixture in testImages/expected.csv and score it
#   python evaluate.py --risk   per-set report of cards that sit close enough to another
#                               card in the same set to be confusable
#
# Fixtures are listed in testImages/expected.csv, one row per image:
#
#   image     filename under testImages/
#   setid     the set the image is scanned against
#   kind      raw    = a photograph, so the contour and warp code runs first
#             warped = an already-warped card, so only hashing and matching run
#   expect    a card number, or 'nomatch' if nothing should be recognised,
#             or 'nocontour' if no four-sided contour should be found at all
#   note      why this fixture exists
#
# Exit code is 0 when every fixture behaves as expected and 1 otherwise, so a broken run is
# distinguishable from a passing one without reading the images by hand.
import argparse
import contextlib
import csv
import io
import itertools
import os
import statistics
import sys

import cv2
import numpy as np
from PIL import Image
import imagehash

import cardData
import cardSets
import utils

TESTDIR = 'testImages'
MANIFEST = os.path.join(TESTDIR, 'expected.csv')
FAILDIR = os.path.join('debugOutput', 'failures')


# Warps a photograph to a flat card, mirroring the image path of main.readCard()
# Returns (warpedImage, None) or (None, reason)
def warpPhoto(path):
    pic = cv2.imread(path)
    if pic is None:
        return None, 'could not read file'

    gray = cv2.cvtColor(pic, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(gray, (3, 3), 0)
    edged = cv2.Canny(blurred, 100, 200)
    kernel = np.ones((5, 5))
    thresh = cv2.erode(cv2.dilate(edged, kernel, iterations=2), kernel, iterations=1)

    contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    corners, _area = utils.biggestContour(contours)
    if len(corners) != 4:
        return None, 'no 4-sided contour found'

    pts = utils.reorderCorners([corners[i][0] for i in range(4)])
    width, height = utils.getWidthCard(), utils.getHeightCard()
    matrix = cv2.getPerspectiveTransform(
        np.float32(pts),
        np.float32([[0, 0], [width, 0], [0, height], [width, height]]))
    return cv2.warpPerspective(pic, matrix, (width, height)), None


# The four hashes compareCards() expects, from an OpenCV BGR image
def hashWarped(warped):
    scanned = Image.fromarray(cv2.cvtColor(warped, cv2.COLOR_BGR2RGB))
    hashes = np.empty(4, dtype=object)
    hashes[0] = imagehash.average_hash(scanned)
    hashes[1] = imagehash.whash(scanned)
    hashes[2] = imagehash.phash(scanned)
    hashes[3] = imagehash.dhash(scanned)
    return hashes


# Reads the fixture list, failing loudly on a malformed row rather than skipping it
def loadManifest():
    if not os.path.isfile(MANIFEST):
        raise FileNotFoundError(f'No fixture list at {MANIFEST}')

    fixtures = []
    with open(MANIFEST, newline='', encoding='utf-8') as f:
        for lineno, row in enumerate(csv.DictReader(f), start=2):
            missing = [c for c in ('image', 'setid', 'kind', 'expect') if not row.get(c)]
            if missing:
                raise ValueError(f'{MANIFEST} line {lineno}: missing {", ".join(missing)}')
            if row['kind'] not in ('raw', 'warped'):
                raise ValueError(f"{MANIFEST} line {lineno}: kind must be raw or warped, "
                                 f"not '{row['kind']}'")
            expect = row['expect']
            if expect not in ('nomatch', 'nocontour'):
                try:
                    expect = int(expect)
                except ValueError:
                    raise ValueError(f"{MANIFEST} line {lineno}: expect must be a card number, "
                                     f"'nomatch' or 'nocontour', not '{row['expect']}'")
            fixtures.append({'image': row['image'], 'setid': row['setid'],
                             'kind': row['kind'], 'expect': expect,
                             'note': row.get('note', '')})
    return fixtures


# Runs one fixture through the pipeline and returns (outcome, distance, detail)
# outcome is a card number, 'nomatch' or 'nocontour'
def runFixture(fixture):
    path = os.path.join(TESTDIR, fixture['image'])
    if not os.path.isfile(path):
        return None, None, 'file is missing'

    if fixture['kind'] == 'raw':
        warped, err = warpPhoto(path)
        if err == 'no 4-sided contour found':
            return 'nocontour', None, err
        if err:
            return None, None, err
    else:
        warped = cv2.imread(path)
        if warped is None:
            return None, None, 'could not read file'

    hashes = hashWarped(warped)

    # compareCards() prints the winning distance; capture it rather than let it interleave
    # with this report, and reuse it as the reported distance
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        cardinfo = cardData.compareCards(hashes, fixture['setid'])
    printed = buffer.getvalue().strip().splitlines()
    distance = int(printed[-1]) if printed and printed[-1].lstrip('-').isdigit() else None

    if cardinfo is None:
        return 'nomatch', distance, warped
    return cardinfo['Card Number'], distance, warped


def reportFixtures():
    fixtures = loadManifest()
    bySet = {}
    for fixture in fixtures:
        bySet.setdefault(fixture['setid'], []).append(fixture)

    os.makedirs(FAILDIR, exist_ok=True)
    allPassed = True
    totals = {'pass': 0, 'fail': 0}

    for setid in sorted(bySet):
        setdef = cardSets.loadSet(setid)
        cardData.ensureSetIndexed(setid)
        names = {c['cardnumber']: c['cardname'] for c in setdef.cards}

        print(f'=== {setdef.name} [{setid}] — cutoff {setdef.cutoff} ===')
        # Positives are fixtures that should resolve to a card; they drive top-1 accuracy.
        # Negatives should not resolve; a match there is a false match.
        positives = negatives = correct = falseMatch = 0

        for fixture in sorted(bySet[setid], key=lambda f: f['image']):
            outcome, distance, detail = runFixture(fixture)
            expect = fixture['expect']
            wantsCard = expect not in ('nomatch', 'nocontour')

            if wantsCard:
                positives += 1
            else:
                negatives += 1

            passed = outcome == expect
            if passed:
                if wantsCard:
                    correct += 1
            else:
                allPassed = False
                if wantsCard is False and outcome not in ('nomatch', 'nocontour'):
                    falseMatch += 1

            totals['pass' if passed else 'fail'] += 1

            got = (f'#{outcome} {names.get(outcome, "?")}'
                   if isinstance(outcome, int) else str(outcome))
            want = (f'#{expect} {names.get(expect, "?")}'
                    if isinstance(expect, int) else str(expect))
            shown = f'{distance}' if distance is not None else '-'
            mark = 'pass' if passed else 'FAIL'
            print(f'  {mark}  {fixture["image"]:<38} dist {shown:>3}  got {got:<20}')
            if not passed:
                print(f'        expected {want}'
                      + (f' — {detail}' if isinstance(detail, str) else ''))
                # Keep the warped image of a failure so it can be looked at afterwards
                if not isinstance(detail, str) and detail is not None:
                    out = os.path.join(FAILDIR, f'{setid}-{fixture["image"]}')
                    cv2.imwrite(out, detail)
                    print(f'        warped image written to {out}')

        if positives:
            print(f'  top-1 accuracy: {correct}/{positives} '
                  f'({100.0 * correct / positives:.0f}%)')
        if negatives:
            print(f'  false matches: {falseMatch}/{negatives}')
        print()

    print(f'{totals["pass"]} passed, {totals["fail"]} failed')
    if not allPassed:
        print('\nA failure means the fixture did not do what expected.csv says it should. '
              'Either the scanner regressed or the expectation is wrong — check which.')
    return 0 if allPassed else 1


# Distance between two cards under the metric compareCards() uses:
# per hashing method the best match across the other card's four orientations, then the worst method
def cardDistance(a, b):
    return max(min(a[m][0] - h for h in b[m]) for m in range(4))


# A scan of the right card lands roughly 8-12 away from it, so a card whose nearest same-set
# neighbour is within that range can lose to it once scan noise is added
RISKBAND = 12


def reportRisk():
    for setid in cardSets.listSetIds():
        setdef = cardSets.loadSet(setid)
        cardData.ensureSetIndexed(setid)
        names = {c['cardnumber']: c['cardname'] for c in setdef.cards}
        cards = cardData.getSetHashes(setid)

        if len(cards) < 2:
            continue

        nearest = {}
        for (na, ha), (nb, hb) in itertools.combinations(cards, 2):
            d = cardDistance(ha, hb)
            for this, other in ((na, nb), (nb, na)):
                if d < nearest.get(this, (999, None))[0]:
                    nearest[this] = (d, other)

        vals = sorted(v[0] for v in nearest.values())
        risky = sorted(((d, n, other) for n, (d, other) in nearest.items() if d <= RISKBAND))

        print(f'=== {setdef.name} [{setid}] — {len(cards)} cards, cutoff {setdef.cutoff} ===')
        print(f'  nearest-impostor distance: min {vals[0]} | median {statistics.median(vals)} '
              f'| max {vals[-1]}')
        print(f'  cards within {RISKBAND} of another card in the set: {len(risky)}/{len(cards)}')
        for d, n, other in risky[:12]:
            print(f'    {d:>3}  {f"#{n} {names[n]}":<26} nearest: #{other} {names[other]}')
        if len(risky) > 12:
            print(f'    ... and {len(risky) - 12} more')
        if not risky:
            print('    none — every card is comfortably separated')
        print()


def main():
    parser = argparse.ArgumentParser(
        description='Measure scanner recognition accuracy against labelled fixtures.')
    parser.add_argument('--risk', action='store_true',
                        help='Report cards that sit close to another card in the same set, '
                             'instead of running the fixtures')
    args = parser.parse_args()

    if args.risk:
        reportRisk()
        return 0
    return reportFixtures()


if __name__ == '__main__':
    sys.exit(main())
