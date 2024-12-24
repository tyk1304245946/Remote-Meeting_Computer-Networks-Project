'''
Simple util implementation for video conference
Including data capture, image compression and image overlap
Note that you can use your own implementation as well :)
'''
from io import BytesIO
import pyaudio
import cv2
import pyautogui
import struct
import numpy as np
from PIL import Image, ImageGrab, UnidentifiedImageError
from config import *
import subprocess
from PIL import Image
import ffmpeg


# audio setting
FORMAT = pyaudio.paInt16
audio = pyaudio.PyAudio()
streamin = audio.open(format=FORMAT, channels=CHANNELS, rate=RATE, input=True, frames_per_buffer=CHUNK)
streamout = audio.open(format=FORMAT, channels=CHANNELS, rate=RATE, output=True, frames_per_buffer=CHUNK)

# print warning if no available camera
cap = cv2.VideoCapture(0)
if cap.isOpened():
    can_capture_camera = True
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, camera_width)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, camera_height)
else:
    can_capture_camera = False

# my_screen_size = pyautogui.size()

# 1920x1080
my_screen_size = (1920, 1080)


def resize_image_to_fit_screen(image, my_screen_size):
    screen_width, screen_height = my_screen_size

    original_width, original_height = image.size

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
    resized_image = image.resize((new_width, new_height), Image.LANCZOS)

    return resized_image


def overlay_camera_images(screen_image, camera_images):
    """
    screen_image: PIL.Image
    camera_images: list[PIL.Image]
    """
    if screen_image is None and camera_images is None:
        black_background = Image.fromarray(np.zeros((my_screen_size[1], my_screen_size[0], 3), dtype=np.uint8), 'RGB')
        return black_background
    if screen_image is not None:
        screen_image = resize_image_to_fit_screen(screen_image, my_screen_size)

    if camera_images is not None:
        # make sure same camera images
        if not all(img.size == camera_images[0].size for img in camera_images):
            raise ValueError("All camera images must have the same size")

        screen_width, screen_height = my_screen_size if screen_image is None else screen_image.size
        camera_width, camera_height = camera_images[0].size

        # calculate num_cameras_per_row
        num_cameras_per_row = screen_width // camera_width

        # adjust camera_imgs
        if len(camera_images) > num_cameras_per_row:
            adjusted_camera_width = screen_width // len(camera_images)
            adjusted_camera_height = (adjusted_camera_width * camera_height) // camera_width
            camera_images = [img.resize((adjusted_camera_width, adjusted_camera_height), Image.LANCZOS) for img in
                                camera_images]
            camera_width, camera_height = adjusted_camera_width, adjusted_camera_height
            num_cameras_per_row = len(camera_images)

        # if no screen_img, create a container
        if screen_image is None:
            display_image = Image.fromarray(np.zeros((camera_width, my_screen_size[1], 3), dtype=np.uint8))
        else:
            display_image = screen_image
        # cover screen_img using camera_images
        for i, camera_image in enumerate(camera_images):
            row = i // num_cameras_per_row
            col = i % num_cameras_per_row
            x = col * camera_width
            y = row * camera_height
            display_image.paste(camera_image, (x, y))

        return display_image
    else:
        return screen_image


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
    return Image.fromarray(frame)


def capture_voice():
    return streamin.read(CHUNK)

def play_audio(audio_data):
    streamout.write(audio_data)


def compress_image(frame, format='JPEG', quality=50):
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

def decompress_image(image_bytes):
    """
    Decompress bytes to PIL.Image.
    """
    img_byte_arr = BytesIO(image_bytes)
    try:
        image = Image.open(img_byte_arr)
        image.load()  # Force loading the image to check if it's valid
    except UnidentifiedImageError:
        print("The image file could not be identified.")
        return None
    return image

def compress_screen(frame, quality=28):
    """
    Compress image using ffmpeg's h.264 encoding and output bytes.

    :param frame: PIL.Image, input image
    :param quality: int, CRF value for compression (0-51), lower means better quality
    :return: bytes, compressed image data
    """

    # Convert PIL Image to raw bytes
    raw_image = np.array(frame)
    height, width, _ = raw_image.shape
    raw_bytes = raw_image.tobytes()

    # Use ffmpeg-python for h.264 encoding
    process = (
        ffmpeg
        .input('pipe:0', format='rawvideo', pix_fmt='rgb24', s=f'{width}x{height}')
        .output('pipe:1', vcodec='libx264', crf=quality, preset='veryfast', format='h264')
        .run_async(pipe_stdin=True, pipe_stdout=True, pipe_stderr=True)
    )
    out, err = process.communicate(input=raw_bytes)

    if process.returncode != 0:
        raise Exception(f'FFmpeg encoding failed: {err.decode()}')

    # Add width and height to output bytes
    header = struct.pack('II', width, height)
    return header + out

def decompress_screen(encoded_bytes):
    """
    Decode H.264 encoded bytes back to an image without specifying width and height.
    """
    # 解压前8个字节获取宽度和高度
    width, height = struct.unpack('II', encoded_bytes[:8])
    encoded_data = encoded_bytes[8:]

    # Use ffmpeg-python to decode the video
    process = (
        ffmpeg
        .input('pipe:0', format='h264')
        .output('pipe:1', format='rawvideo', pix_fmt='rgb24', s=f'{width}x{height}')
        .run_async(pipe_stdin=True, pipe_stdout=True, pipe_stderr=True)
    )
    out, err = process.communicate(input=encoded_data)

    if process.returncode != 0:
        raise Exception(f'FFmpeg decoding failed: {err.decode()}')

    raw_image = np.frombuffer(out, np.uint8).reshape((height, width, 3))
    image = Image.fromarray(raw_image, 'RGB')
    return image
