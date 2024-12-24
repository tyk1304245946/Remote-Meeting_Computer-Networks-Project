'''
Simple util implementation for video conference
Including data capture, image compression and image overlap
Note that you can use your own implementation as well :)
'''
from io import BytesIO
import pyaudio
import cv2
import pyautogui
import numpy as np
from PIL import Image, ImageGrab, UnidentifiedImageError
from config import *
import mss
import mss.tools


# audio setting
# FORMAT = pyaudio.paInt16
# audio = pyaudio.PyAudio()
# streamin = audio.open(format=FORMAT, channels=CHANNELS, rate=RATE, input=True, frames_per_buffer=CHUNK)
# streamout = audio.open(format=FORMAT, channels=CHANNELS, rate=RATE, output=True, frames_per_buffer=CHUNK)

# print warning if no available camera
cap = cv2.VideoCapture(0)
if cap.isOpened():
    can_capture_camera = True
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, camera_width)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, camera_height)
else:
    can_capture_camera = False

my_screen_size = pyautogui.size()


def resize_image_to_fit_screen(image, my_screen_size):
    screen_width, screen_height = my_screen_size

    original_height, original_width = image.shape[:2]

    aspect_ratio = original_width / original_height

    if screen_width / screen_height > aspect_ratio:
        # resize according to height
        new_height = screen_height
        new_width = int(new_height * aspect_ratio)
    else:
        # resize according to width
        new_width = screen_width
        new_height = int(new_width / aspect_ratio)

    # resize the image
    resized_image = cv2.resize(image, (new_width, new_height), interpolation=cv2.INTER_AREA)

    return resized_image


def overlay_camera_images(screen_image, camera_images):
    """
    screen_image: np.array
    camera_images: list[np.array]
    """
    if screen_image is None and camera_images is None:
        print('[Warn]: cannot display when screen and camera are both None')
        return None
    if screen_image is not None:
        screen_image = resize_image_to_fit_screen(screen_image, my_screen_size)

    if camera_images is not None:
        # make sure same camera images
        if not all(img.shape == camera_images[0].shape for img in camera_images):
            raise ValueError("All camera images must have the same size")

        screen_height, screen_width = my_screen_size if screen_image is None else screen_image.shape[:2]
        camera_height, camera_width = camera_images[0].shape[:2]

        # calculate num_cameras_per_row
        num_cameras_per_row = screen_width // camera_width

        # adjust camera_imgs
        if len(camera_images) > num_cameras_per_row:
            adjusted_camera_width = screen_width // len(camera_images)
            adjusted_camera_height = (adjusted_camera_width * camera_height) // camera_width
            camera_images = [cv2.resize(img, (adjusted_camera_width, adjusted_camera_height), interpolation=cv2.INTER_AREA) for img in camera_images]
            camera_width, camera_height = adjusted_camera_width, adjusted_camera_height
            num_cameras_per_row = len(camera_images)

        # if no screen_img, create a container
        if screen_image is None:
            display_image = np.zeros((camera_height, my_screen_size[0], 3), dtype=np.uint8)
        else:
            display_image = screen_image
        # cover screen_img using camera_images
        for i, camera_image in enumerate(camera_images):
            row = i // num_cameras_per_row
            col = i % num_cameras_per_row
            x = col * camera_width
            y = row * camera_height
            display_image[y:y+camera_height, x:x+camera_width] = camera_image

        return display_image
    else:
        return


def capture_screen():
    screen = ImageGrab.grab()
    screen_image = np.array(screen)
    screen_image = cv2.resize(screen_image, (1920, 1080), interpolation=cv2.INTER_AREA)
    return screen_image


def capture_camera():
    # capture frame of camera
    ret, frame = cap.read()
    if not ret:
        raise Exception('Fail to capture frame from camera')
    frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    camera_image = Image.fromarray(frame)
    return camera_image


def capture_voice():
    return streamin.read(CHUNK)

def play_audio(audio_data):
    streamout.write(audio_data)


def compress_image(frame, format='JPEG', quality=85):
    """
    compress image and output Bytes

    :param image: PIL.Image, input image
    :param format: str, output format ('JPEG', 'PNG', 'WEBP', ...)
    :param quality: int, compress quality (0-100), 85 default
    :return: bytes, compressed image data
    """
    _, encoded_frame = cv2.imencode('.jpg', np.array(frame), [int(cv2.IMWRITE_JPEG_QUALITY), quality])
    payload = encoded_frame.tobytes()
    return payload

def decompress_image(payload):
    np_arr = np.frombuffer(payload, np.uint8)
    image = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
    return image
