#!/usr/bin/env python

import rospy
import numpy
import cv2
from cv_bridge import CvBridge
from sensor_msgs.msg import Image
from deepracer_interfaces_pkg.msg import RoadLaneInfo

line_latest_valid_right_border = []
line_latest_valid_left_border = []


# is a line defined with two points on the left side of an image
# defined with a hight and width ?
def is_line_entirly_on_left_side(height, width, line):
    x1, y1, x2, y2 = line.reshape(4)
    if x1 <= width/2 and x2 <= width/2:
        return True
    else:
        return False


# is a line defined with two points on the right side of an image
# defined with a hight and width ?
def is_line_entirly_on_right_side(height, width, line):
    x1, y1, x2, y2 = line.reshape(4)
    if x1 > width/2 and x2 > width/2:
        return True
    else:
        return False


# what part of the image from top to be masked
# this is important to hide the un-wanted horizon and
# focus on the ground
def view_mask_hight(height, width):
    return int(height/3)


# A polygon represening the visibility winodw to be used as a mask
# on the captured image. The mask should ficus on the part of the
# ground which contains the lanes.
def view_mask(height, width, turn_skew):
    H = height-1
    W = width-1
    shoulder_skew = int(turn_skew/2)
    depth = view_mask_hight(height, width)
    return [
        (0, H),
        (W, H),
        (W, (H-150+shoulder_skew)),
        (430-turn_skew, depth),
        (210-turn_skew, depth),
        ((0), (H-150-shoulder_skew)), (0, H)]


# creates two-points line from slopw/intercept
# we limit the lines to start from tgh eimage buttom (hight)
# and end in the middle of the image
def make_coordinates(height, width, line_slope_and_intercept):
    slope, intercept = line_slope_and_intercept
    y1 = height
    y2 = view_mask_hight(height, width)
    x1 = int((y1-intercept)/slope)
    x2 = int((y2-intercept)/slope)
    return numpy.array([x1, y1, x2, y2])


# puts a mask on the image
# the mask is a polygon defined by view_mask
def mask_image(image, turn_skew):
    height = image.shape[0]
    width = image.shape[1]
    polygons = numpy.array([
        view_mask(height, width, turn_skew)],
        dtype=numpy.int32)

    mask = numpy.zeros_like(image)
    cv2.fillPoly(mask, polygons, 255)
    masked_image = cv2.bitwise_and(mask, image)
    return masked_image


# creates a grayscale-version from the image then enforces a derivative on it.
# Having a gradient image, those parts with obious change of color can be
# easily identified
def canny(image):
    image_gs = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)
    # blur the image using a gaussian blurr matrix of size 5x5
    image_blurred = cv2.GaussianBlur(image_gs, (5, 5), 0)
    # compute the gradient (derivative) of the blurred image
    image_gradient = cv2.Canny(image_blurred, 50, 150)
    return image_gradient


# extract two lanes from the lines detected from the images
# here, we assume we have a view of the camera inside a road with
# a lane on our left and another lane on our right
# we then split the lines two two groups based on their slopes
#
# @image: an rgb image captured by the front camera
# @turn_skew: a value between -1.0 and 1.0 to represent the expected turn of the lane
def get_two_lanes(image, turn_skew):

    height = image.shape[0]
    width = image.shape[1]

    # put the skew in the range -75 to 75 as required by the mask function
    turn_skew = turn_skew*75.0

    # use canny to make a gradient image
    image_grad = canny(image)

    # mask the image to focus only on the lane area
    image_masked = mask_image(image_grad, turn_skew)

    # extract the lines the the masked region
    lines = cv2.HoughLinesP(image_masked, 2, numpy.pi/180.0, 100,
        numpy.array([]), minLineLength=40, maxLineGap=5)

    # split the lines to left/right sides (with acceptable slopes)
    # exclude horizontal-close lines
    right_lines = []
    left_lines = []
    if lines is not None:
        for line in lines:
            x1, y1, x2, y2 = line.reshape(4)
            params = numpy.polyfit((x1, x2), (y1, y2), 1.0)
            slope = params[0]
            intercept = params[1]

            # filter any horizontal-close lines (those in the range -/+ 20 deg)
            if slope >= -0.35 and slope <= 0.35:
                continue

            if slope <= 0 and is_line_entirly_on_left_side(height, width, line):
                left_lines.append((slope, intercept))
            else:
                if is_line_entirly_on_right_side(height, width, line):
                    right_lines.append((slope, intercept))

    # do we have a right lane ?
    if len(right_lines) == 0:
        has_right = False
        right_lane = numpy.array([0, 0, 0, 0])
    else:
        has_right = True
        right_lane_avg = numpy.average(right_lines, axis=0)
        right_lane = make_coordinates(height, width, right_lane_avg)

    # do we have a left lane ?
    if len(left_lines) == 0:
        has_left = False
        left_lane = numpy.array([0, 0, 0, 0])
    else:
        has_left = True
        left_lane_avg = numpy.average(left_lines, axis=0)
        left_lane = make_coordinates(height, width, left_lane_avg)

    return has_left, has_right, left_lane.tolist(), right_lane.tolist()


def lane_detection_callback(data):

    global line_latest_valid_right_border
    global line_latest_valid_left_border

    image_rgb = bridge.imgmsg_to_cv2(data, "bgr8")
    has_left, has_right, left_lane, right_lane = get_two_lanes(image_rgb, 0.0)

    msg = RoadLaneInfo()
    msg.src_img_msg_seq = data.header.seq
    msg.found_right_border = has_right
    msg.found_left_border = has_left
    msg.num_lanes = 1
    msg.current_lane = 0
    msg.lanes_start_offset = [0.0]
    msg.line_right_border = right_lane
    msg.line_left_border = left_lane

    if has_right:
        line_latest_valid_right_border = right_lane
        msg.line_latest_valid_right_border = right_lane
    else:
        msg.line_latest_valid_right_border = line_latest_valid_right_border

    if has_left:
        line_latest_valid_left_border = left_lane
        msg.line_latest_valid_left_border = left_lane
    else:
        msg.line_latest_valid_left_border = line_latest_valid_left_border

    road_lane_pub.publish(msg)


if __name__ == '__main__':
    try:
        bridge = CvBridge()
        road_lane_pub = rospy.Publisher('road_lanes', RoadLaneInfo, queue_size=10)
        rospy.init_node('lanedetector', anonymous=False)
        image_sub = rospy.Subscriber("video_mjpeg", Image, lane_detection_callback)
        rospy.loginfo("Started the lanedetector node. We wait for video frames "\
            "from /video_mjpeg and publish detected lanes to /road_lanes.")

        rospy.spin()
    except rospy.ROSInterruptException:
        pass