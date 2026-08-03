# Headless check of the scan -> hash -> match pipeline for every image in testImages/.
# Mirrors the image-file path of main.readCard() but skips all cv2.imshow() calls.
# Usage: python test_headless.py [setid]   (defaults to evolutions)
import os
import sys
import cv2
import numpy as np
from PIL import Image
import imagehash
import cardData
import utils


def scanImage(pathImage):
    pic = cv2.imread(pathImage)
    if pic is None:
        return None, 'could not read file'

    grayFrame = cv2.cvtColor(pic, cv2.COLOR_BGR2GRAY)
    blurredFrame = cv2.GaussianBlur(grayFrame, (3, 3), 0)
    edgedFrame = cv2.Canny(image=blurredFrame, threshold1=100, threshold2=200)

    kernel = np.ones((5, 5))
    frameDial = cv2.dilate(edgedFrame, kernel, iterations=2)
    frameThreshold = cv2.erode(frameDial, kernel, iterations=1)

    contours, _ = cv2.findContours(frameThreshold, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    corners, maxArea = utils.biggestContour(contours)
    if len(corners) != 4:
        return None, 'no 4-sided contour found'

    corners = [corners[0][0], corners[1][0], corners[2][0], corners[3][0]]
    corners = utils.reorderCorners(corners)
    widthCard, heightCard = utils.getWidthCard(), utils.getHeightCard()
    pts1 = np.float32(corners)
    pts2 = np.float32([[0, 0], [widthCard, 0], [0, heightCard], [widthCard, heightCard]])
    matrix = cv2.getPerspectiveTransform(pts1, pts2)
    return cv2.warpPerspective(pic, matrix, (widthCard, heightCard)), None


def main():
    setid = sys.argv[1] if len(sys.argv) > 1 else 'evolutions'
    cardData.ensureSetIndexed(setid)
    print(f'Scanning against set: {setid}')

    for name in sorted(os.listdir('testImages')):
        path = os.path.join('testImages', name)
        print(f'\n=== {name} ===')

        warped, err = scanImage(path)
        if err:
            print(f'  FAIL: {err}')
            continue

        # Save the warped card so the perspective correction can be eyeballed afterwards
        os.makedirs('debugOutput', exist_ok=True)
        cv2.imwrite(os.path.join('debugOutput', f'warped_{name}'), warped)

        scannedCard = Image.fromarray(cv2.cvtColor(warped, cv2.COLOR_BGR2RGB))
        hashes = np.empty(4, dtype=object)
        hashes[0] = imagehash.average_hash(scannedCard)
        hashes[1] = imagehash.whash(scannedCard)
        hashes[2] = imagehash.phash(scannedCard)
        hashes[3] = imagehash.dhash(scannedCard)

        print('  min hash distance: ', end='')
        cardinfo = cardData.compareCards(hashes, setid)
        if cardinfo is None:
            print('  NO MATCH (above cutoff)')
        else:
            print(f"  MATCH: #{cardinfo['Card Number']} {cardinfo['Card Name']} "
                  f"({cardinfo['Rarity']}, {cardinfo['Card Type']}) "
                  f"| pokemon={cardinfo['Pokemon']} dex={cardinfo['Pokedex Number']}")


if __name__ == '__main__':
    main()
