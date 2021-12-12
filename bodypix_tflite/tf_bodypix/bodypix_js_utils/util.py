# based on:
# https://github.com/tensorflow/tfjs-models/blob/body-pix-v2.0.4/body-pix/src/util.ts

import logging
import math
from collections import namedtuple
from typing import List, Tuple, Union

# import tensorflow as tf
from PIL import Image
import numpy as np

from .types import Keypoint, Pose, Vector2D


LOGGER = logging.getLogger(__name__)


Padding = namedtuple('Padding', ('top', 'bottom', 'left', 'right'))


# see isValidInputResolution
def is_valid_input_resolution(
    resolution: Union[int, float], output_stride: int
) -> bool:
    return (resolution - 1) % output_stride == 0


# see toValidInputResolution
def to_valid_input_resolution(
    input_resolution: Union[int, float], output_stride: int
) -> int:
    if is_valid_input_resolution(input_resolution, output_stride):
        return int(input_resolution)

    return int(math.floor(input_resolution / output_stride) * output_stride + 1)


# see toInputResolutionHeightAndWidth
def get_bodypix_input_resolution_height_and_width(
    internal_resolution_percentage: float,
    output_stride: int,
    input_height: int,
    input_width: int
) -> Tuple[int, int]:
    return (
        to_valid_input_resolution(
            input_height * internal_resolution_percentage, output_stride),
        to_valid_input_resolution(
            input_width * internal_resolution_percentage, output_stride)
    )


# see padAndResizeTo
def pad_and_resize_to(
    image: np.ndarray,
    target_height, target_width: int
) -> Tuple[np.ndarray, Padding]:
    input_height, input_width = image.shape[:2]
    target_aspect = target_width / target_height
    aspect = input_width / input_height
    if aspect < target_aspect:
        # pads the width
        padding = Padding(
            top=0,
            bottom=0,
            left=round(0.5 * (target_aspect * input_height - input_width)),
            right=round(0.5 * (target_aspect * input_height - input_width))
        )
    else:
        # pads the height
        padding = Padding(
            top=round(0.5 * ((1.0 / target_aspect) * input_width - input_height)),
            bottom=round(0.5 * ((1.0 / target_aspect) * input_width - input_height)),
            left=0,
            right=0
        )
    padded = pad_image_like_tensorflow(image=image, padding=padding)

    resized = resize_like_tensorflow(image=padded, new_size=(target_width, target_height))

    return resized, padding


def resize_like_tensorflow(image, new_size):
    """
    This is my function to resize image like tensorflow
    :param image:
    :param new_size: (target_width, target_height)
    :return:
    """

    pil_img = Image.fromarray(image.astype('uint8'), 'RGB')

    pil_resized = pil_img.resize(size=new_size, resample=Image.BILINEAR)

    resized_image = np.asarray(pil_resized, dtype='float32')

    return resized_image


def pad_image_like_tensorflow(image, padding):
    """
    This is my padding function to replace with tf.image.pad_to_bounding_box
    :param image:
    :param padding:
    :return:
    """

    padded = np.copy(image)
    dims = padded.shape

    if padding.top != 0:
        top_zero_row = np.zeros(shape=(padding.top, dims[1], dims[2]))
        padded = np.vstack([top_zero_row, padded])

    if padding.bottom != 0:
        bottom_zero_row = np.zeros(shape=(padding.top, dims[1], dims[2]))
        padded = np.vstack([padded, bottom_zero_row])

    dims = padded.shape
    if padding.left != 0:
        left_zero_column = np.zeros(shape=(dims[0], padding.left, dims[2]))
        padded = np.hstack([left_zero_column, padded])

    if padding.right != 0:
        right_zero_column = np.zeros(shape=(dims[0], padding.right, dims[2]))
        padded = np.hstack([padded, right_zero_column])

    return padded


ZERO_VECTOR_2D = Vector2D(x=0, y=0)


def _scale_and_offset_vector(
    vector: Vector2D, scale_vector: Vector2D, offset_vector: Vector2D
) -> Vector2D:
    return Vector2D(
        x=vector.x * scale_vector.x + offset_vector.x,
        y=vector.y * scale_vector.y + offset_vector.y
    )


def scalePose(
    pose: Pose, scale_vector: Vector2D, offset_vector: Vector2D
) -> Pose:
    return Pose(
        score=pose.score,
        keypoints={
            keypoint_id: Keypoint(
                score=keypoint.score,
                part=keypoint.part,
                position=_scale_and_offset_vector(
                    keypoint.position,
                    scale_vector,
                    offset_vector
                )
            )
            for keypoint_id, keypoint in pose.keypoints.items()
        }
    )


def scalePoses(
    poses: List[Pose], scale_vector: Vector2D, offset_vector: Vector2D
) -> List[Pose]:
    if (
        scale_vector.x == 1
        and scale_vector.y == 1
        and offset_vector.x == 0
        and offset_vector.y == 0
    ):
        return poses
    return [
        scalePose(pose, scale_vector, offset_vector)
        for pose in poses
    ]


def flipPosesHorizontal(poses: List[Pose], imageWidth: int) -> List[Pose]:
    if imageWidth <= 0:
        return poses
    scale_vector = Vector2D(x=-1, y=1)
    offset_vector = Vector2D(x=imageWidth - 1, y=0)
    return scalePoses(
        poses,
        scale_vector,
        offset_vector
    )


def scaleAndFlipPoses(
    poses: List[Pose],
    height: int,
    width: int,
    inputResolutionHeight: int,
    inputResolutionWidth: int,
    padding: Padding,
    flipHorizontal: bool
) -> List[Pose]:
    scale_vector = Vector2D(
        y=(height + padding.top + padding.bottom) / (inputResolutionHeight),
        x=(width + padding.left + padding.right) / (inputResolutionWidth)
    )
    offset_vector = Vector2D(
        x=-padding.left,
        y=-padding.top
    )

    LOGGER.debug('height: %s', height)
    LOGGER.debug('width: %s', width)
    LOGGER.debug('inputResolutionHeight: %s', inputResolutionHeight)
    LOGGER.debug('inputResolutionWidth: %s', inputResolutionWidth)
    LOGGER.debug('scale_vector: %s', scale_vector)
    LOGGER.debug('offset_vector: %s', offset_vector)

    scaledPoses = scalePoses(
        poses, scale_vector, offset_vector
    )

    if flipHorizontal:
        return flipPosesHorizontal(scaledPoses, width)
    return scaledPoses