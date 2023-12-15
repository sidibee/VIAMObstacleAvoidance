import asyncio
import time
import random
import cv2
import numpy as np
from PIL import Image
import io
import os
from datetime import datetime

from viam.robot.client import RobotClient
from viam.rpc.dial import Credentials, DialOptions
from viam.services.vision import VisionClient
from viam.components.camera import Camera
from viam.components.base import Base
import viam.components as components

async def connect():
    opts = RobotClient.Options.with_api_key(
        api_key='9p7myf1tuq9gcsk6ekizcwtsi9jf1m2a',
        api_key_id='f26862d0-4261-472b-bec8-5e7de0116f2e'
    )
    return await RobotClient.at_address('pi-main.h67pds74mq.viam.cloud', opts)

async def analyze_environment(camera, obstacle_threshold, minimum_area, depth_threshold):
    frame = await camera.get_image(mime_type="image/jpeg")
    image_np = np.array(frame)

    # Apply Gaussian Blur to reduce noise
    blurred_image = cv2.GaussianBlur(image_np, (5, 5), 0)

    # Convert the blurred image to grayscale
    gray_image = cv2.cvtColor(blurred_image, cv2.COLOR_BGR2GRAY)

    # Edge detection to identify potential obstacles
    edges = cv2.Canny(gray_image, 100, 200)

    # Dilate the edges to make them more pronounced
    dilated_edges = cv2.dilate(edges, None, iterations=1)

    # Find contours from the dilated edges
    contours, _ = cv2.findContours(dilated_edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    # Draw contours on the image, but only for those that are above a minimum area size
    # and add depth estimation based on the size of contours
    obstacles_with_depth = []
    for contour in contours:
        area = cv2.contourArea(contour)
        if area > minimum_area:
            cv2.drawContours(image_np, [contour], -1, (0, 255, 0), 3)
            if area > depth_threshold:
                obstacles_with_depth.append((contour, 'close'))
            else:
                obstacles_with_depth.append((contour, 'far'))

    # Divide the image into left, center, and right sections for direction decision
    height, width = edges.shape
    left_edge = edges[:, :width // 3]
    center_edge = edges[:, width // 3:2 * width // 3]
    right_edge = edges[:, 2 * width // 3:]

    # Count the edge points in each section
    left_count = cv2.countNonZero(left_edge)
    center_count = cv2.countNonZero(center_edge)
    right_count = cv2.countNonZero(right_edge)

    # Calculate the ratio of edge points to total points in each section
    total_points = (height * width) // 3
    left_ratio = left_count / total_points
    center_ratio = center_count / total_points
    right_ratio = right_count / total_points

    # Save the image with contours to the desktop/debugimages folder
    desktop_path = os.path.join(os.path.expanduser('~'), 'Desktop')
    debug_folder_path = os.path.join(desktop_path, 'debugimages')
    if not os.path.exists(debug_folder_path):
        os.makedirs(debug_folder_path)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S%f")
    debug_image_path = os.path.join(debug_folder_path, f'debug_image_{timestamp}.jpg')
    cv2.imwrite(debug_image_path, image_np)

    # Determine the direction based on the edge ratios
    close_obstacles = [obst for obst in obstacles_with_depth if obst[1] == 'close']
    if close_obstacles:
        return 'avoid_close_obstacle'
    elif center_ratio < obstacle_threshold:
        return 'forward'
    elif left_ratio < right_ratio:
        return 'left'
    else:
        return 'right'

async def main():
    vel = 100  # Speed
    move_distance = 50  # Distance in units
    turn_angle = 90  # Degrees to turn when avoiding an obstacle
    obstacle_threshold = 0.15  # Edge ratio threshold for obstacles
    minimum_area = 10000 # Minimum area for a contour to be considered an obstacle
    depth_threshold = 20000  # Depth threshold for close obstacles

    robot = await connect()
    base = Base.from_robot(robot, "viam_base")
    camera = Camera.from_robot(robot, "yo1")

    for _ in range(400):  # Replace with a condition to continue running as needed
        direction = await analyze_environment(camera, obstacle_threshold, minimum_area, depth_threshold)

        if direction == 'forward':
            print("Moving forward")
            await base.move_straight(move_distance, vel)
        elif direction == 'avoid_close_obstacle':
            print("Close obstacle detected, avoiding...")
            while direction == 'avoid_close_obstacle':
                # Randomly choose direction to turn
                turn_degrees = turn_angle if random.choice([True, False]) else -turn_angle
                await base.spin(turn_degrees, vel)
                # Check if obstacle is still close after turning
                direction = await analyze_environment(camera, obstacle_threshold, minimum_area, depth_threshold)

            # Move forward slightly after avoiding the close obstacle
            await base.move_straight(move_distance, vel)
        elif direction == 'left':
            print("Turning left")
            await base.spin(-turn_angle, vel)  # Assuming CCW is negative
            await base.move_straight(move_distance, vel)
        elif direction == 'right':
            print("Turning right")
            await base.spin(turn_angle, vel)  # Assuming CW is positive
            await base.move_straight(move_distance, vel)

    await robot.close()

if __name__ == "__main__":
    print("Starting up...")
    asyncio.run(main())
    print("Done.")