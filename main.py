import argparse
import sys
import cv2
import numpy as np
import cardData
import cardSets
import utils


def readCard(setid, liveFeed=True, pathImage='testImages/tiltright.jpg', camIndex=0, rotateFeed=False):
    # setid       Id of the set being scanned against; the folder name under sets/
    # liveFeed    Flag signaling if images are being read live from a webcam or from an image file
    # pathImage   File name of image (only used when liveFeed is False)
    # camIndex    Video source index; 0 = default webcam (the C920 on this machine)
    # rotateFeed  True for a phone in portrait (Iriun); False for a landscape webcam like the C920
    setdef = cardSets.loadSet(setid)
    print(f"Scanning against {setdef.name} ({setdef.numCards} cards).")

    cam = cv2.VideoCapture(camIndex)
    # Request a higher capture resolution so the warped card keeps enough detail for hashing
    cam.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
    cam.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)

    # Scaled to the IRL height and width of a Pokemon card (6.6 cm x 8.8 cm)
    widthCard = utils.getWidthCard()
    heightCard = utils.getHeightCard()

    while True:
        # Create a blank image
        blackImg = np.zeros((heightCard, widthCard, 3), np.uint8)

        # Check if using a live webcam feed or a saved picture
        if liveFeed:
            check, frame = cam.read()
            # A phone in portrait feeds a sideways frame that needs rotating; a landscape webcam does not
            if rotateFeed:
                frame = cv2.rotate(frame, cv2.ROTATE_90_CLOCKWISE)
            rot90frame = cv2.resize(frame, (widthCard, heightCard))
        else:
            # Read in picture and resize it to normalize
            pic = cv2.imread(pathImage)
            rot90frame = pic.copy()

        # Make image gray scale
        grayFrame = cv2.cvtColor(rot90frame, cv2.COLOR_BGR2GRAY)
        # Blur the image to reduce noise
        blurredFrame = cv2.GaussianBlur(grayFrame, (3, 3), 0)

        # Use Canny edge detection to get edges
        edgedFrame = cv2.Canny(image=blurredFrame, threshold1=100, threshold2=200)

        # Clean up edges
        kernel = np.ones((5,5))
        frameDial = cv2.dilate(edgedFrame, kernel, iterations=2)
        frameThreshold = cv2.erode(frameDial, kernel, iterations=1)

        # Get image contours
        contourFrame = rot90frame.copy()
        bigContour = rot90frame.copy()
        contours, hierarchy = cv2.findContours(frameThreshold, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        cv2.drawContours(contourFrame, contours, -1, (0, 255, 0), 10)

        imgWarpColored = blackImg  # Set imgWarpColored
        # Get biggest contour
        corners, maxArea = utils.biggestContour(contours)
        if len(corners) == 4:
            corners = [corners[0][0], corners[1][0], corners[2][0], corners[3][0]]
            corners = utils.reorderCorners(corners)  # Reorders corners to [topLeft, topRight, bottomLeft, bottomRight]
            #cv2.drawContours(bigContour, corners, -1, (0, 255, 0), 10)
            bigContour = utils.drawRectangle(bigContour, corners)
            pts1 = np.float32(corners)
            pts2 = np.float32([[0, 0], [widthCard, 0], [0, heightCard], [widthCard, heightCard]])
            # Makes a matrix that transforms the detected card to a vertical rectangle
            matrix = cv2.getPerspectiveTransform(pts1, pts2)
            # Transforms card to a rectangle widthCard x heightCard
            imgWarpColored = cv2.warpPerspective(rot90frame, matrix, (widthCard, heightCard))

        # Resize all of the images to the same dimensions
        # Note: imgWarpColored is already resized and matchingCard gets resized in utils.getMatchingCard()
        rot90frame = cv2.resize(rot90frame, (widthCard, heightCard))
        grayFrame = cv2.resize(grayFrame, (widthCard, heightCard))
        blurredFrame = cv2.resize(blurredFrame, (widthCard, heightCard))
        edgedFrame = cv2.resize(edgedFrame, (widthCard, heightCard))
        contourFrame = cv2.resize(contourFrame, (widthCard, heightCard))
        bigContour = cv2.resize(bigContour, (widthCard, heightCard))

        # Check if a matching card has been found, and if so, display it
        found, matchingCard = utils.findCard(imgWarpColored.copy(), setid)  # Check to see if a matching card was found

        # An array of all 8 images
        imageArr = ([rot90frame, grayFrame, blurredFrame, edgedFrame],
                    [contourFrame, bigContour, imgWarpColored, matchingCard])

        # Labels for each image
        labels = [["Original", "Gray", "Blurred", "Threshold"],
                  ["Contours", "Biggest Contour", "Warped Perspective", "Matching Card"]]

        # Stack all 8 images into one and add text labels
        stackedImage = utils.makeDisplayImage(imageArr, labels)

        # Display the image
        cv2.imshow(f"Card Finder - {setdef.name}", stackedImage)

        if not liveFeed:  # If reading image file, display image until key is pressed
            if not found:  # If a matching card has not been found
                print('Please try another image. Your card could not be found.')
            cv2.waitKey(0)  # Keeps window open until any key is pressed
            break
        elif cv2.waitKey(1) & 0xFF == ord('q'):  # If reading from video, quit if 'q' is pressed
            break
        elif found:  # If the input is a video and a matching card has been found
            print('\n\nPress any key to exit.')
            cv2.waitKey(0)
            break

    # Stops cameras and closes display window
    cam.release()
    cv2.destroyAllWindows()


# Prints every set found under sets/, marking the ones already indexed into the database
def printSets(sets):
    print('Available sets:')
    for i, s in enumerate(sets, start=1):
        status = '' if cardData.isSetIndexed(s.setid) else '  (not indexed yet)'
        print(f'  {i}. {s.name} [{s.setid}] - {s.numCards} cards{status}')


# Asks the user which set they are scanning from and returns its id
def chooseSet(sets):
    printSets(sets)
    while True:
        answer = input('Which set are you scanning from? (number or id, or q to quit): ').strip()
        if answer.lower() == 'q':
            return None
        if answer.isdigit() and 1 <= int(answer) <= len(sets):
            return sets[int(answer) - 1].setid
        for s in sets:
            if answer.lower() == s.setid.lower():
                return s.setid
        print('Not one of the choices above; try again.')


def main():
    parser = argparse.ArgumentParser(description='Scan a Pokemon card and identify it within a chosen set.')
    parser.add_argument('--set', dest='setid',
                        help='Id of the set to scan against (the folder name under sets/). '
                             'You are asked to pick one if this is left out.')
    parser.add_argument('--list-sets', action='store_true', help='List the available sets and exit')
    parser.add_argument('--image', help='Read this image file instead of the webcam')
    parser.add_argument('--camera', type=int, default=0, help='Webcam index to read from (default 0)')
    parser.add_argument('--rotate', action='store_true',
                        help='Rotate the feed 90 degrees, for a phone camera held in portrait')
    parser.add_argument('--reindex', action='store_true',
                        help='Re-hash the chosen set even if it is already in the database, '
                             'for when its images or cards.csv have changed')
    args = parser.parse_args()

    sets = cardSets.listSets()
    if not sets:
        print(f'No sets found in {cardSets.SETSDIR}/. See the README for how to add one.')
        return 1

    if args.list_sets:
        printSets(sets)
        return 0

    setid = args.setid
    if setid is None:
        setid = chooseSet(sets)
        if setid is None:
            return 0
    elif setid not in [s.setid for s in sets]:
        print(f"No set called '{setid}' in {cardSets.SETSDIR}/.")
        printSets(sets)
        return 1

    # Hashes the set into the database if this is the first time it has been used
    cardData.ensureSetIndexed(setid, force=args.reindex)

    readCard(setid,
             liveFeed=args.image is None,
             pathImage=args.image,
             camIndex=args.camera,
             rotateFeed=args.rotate)
    return 0


if __name__ == '__main__':
    sys.exit(main())
