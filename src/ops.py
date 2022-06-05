import numpy as np
import tensorflow as tf

COLORSPACE_RGB = 'RGB'
COLORSPACE_LAB = 'LAB'
tf.compat.v1nn.softmax_cross_entropy_with_logits

def conv2d(inputs, filters, name, kernel_size=4, strides=2, bnorm=True, activation=None, seed=None):
    """
    Creates a conv2D block
    """
    initializer=tf.compat.v1variance_scaling_initializer(seed=seed)
    res = tf.compat.v1layers.conv2d(
        name=name,
        inputs=inputs,
        filters=filters,
        kernel_size=kernel_size,
        strides=strides,
        padding="same",
        kernel_initializer=initializer)

    if bnorm:
        res = tf.compat.v1layers.batch_normalization(inputs=res, name='bn_' + name, training=True)

    # activation after batch-norm
    if activation is not None:
        res = activation(res)

    return res


def conv2d_transpose(inputs, filters, name, kernel_size=4, strides=2, bnorm=True, activation=None, seed=None):
    """
    Creates a conv2D-transpose block
    """
    initializer=tf.compat.v1variance_scaling_initializer(seed=seed)
    res = tf.compat.v1layers.conv2d_transpose(
        name=name,
        inputs=inputs,
        filters=filters,
        kernel_size=kernel_size,
        strides=strides,
        padding="same",
        kernel_initializer=initializer)

    if bnorm:
        res = tf.compat.v1layers.batch_normalization(inputs=res, name='bn_' + name, training=True)

    # activation after batch-norm
    if activation is not None:
        res = activation(res)

    return res


def pixelwise_accuracy(img_real, img_fake, colorspace, thresh):
    """
    Measures the accuracy of the colorization process by comparing pixels
    """
    img_real = postprocess(img_real, colorspace, COLORSPACE_LAB)
    img_fake = postprocess(img_fake, colorspace, COLORSPACE_LAB)

    diffL = tf.compat.v1abs(tf.compat.v1round(img_real[..., 0]) - tf.compat.v1round(img_fake[..., 0]))
    diffA = tf.compat.v1abs(tf.compat.v1round(img_real[..., 1]) - tf.compat.v1round(img_fake[..., 1]))
    diffB = tf.compat.v1abs(tf.compat.v1round(img_real[..., 2]) - tf.compat.v1round(img_fake[..., 2]))

    # within %thresh of the original
    predL = tf.compat.v1cast(tf.compat.v1less_equal(diffL, 1 * thresh), tf.compat.v1float64)        # L: [0, 100]
    predA = tf.compat.v1cast(tf.compat.v1less_equal(diffA, 2.2 * thresh), tf.compat.v1float64)      # A: [-110, 110]
    predB = tf.compat.v1cast(tf.compat.v1less_equal(diffB, 2.2 * thresh), tf.compat.v1float64)      # B: [-110, 110]

    # all three channels are within the threshold
    pred = predL * predA * predB

    return tf.compat.v1reduce_mean(pred)


def preprocess(img, colorspace_in, colorspace_out):
    if colorspace_out.upper() == COLORSPACE_RGB:
        if colorspace_in == COLORSPACE_LAB:
            img = lab_to_rgb(img)

        # [0, 1] => [-1, 1]
        img = (img / 255.0) * 2 - 1

    elif colorspace_out.upper() == COLORSPACE_LAB:
        if colorspace_in == COLORSPACE_RGB:
            img = rgb_to_lab(img / 255.0)

        L_chan, a_chan, b_chan = tf.compat.v1unstack(img, axis=3)

        # L: [0, 100] => [-1, 1]
        # A, B: [-110, 110] => [-1, 1]
        img = tf.compat.v1stack([L_chan / 50 - 1, a_chan / 110, b_chan / 110], axis=3)

    return img


def postprocess(img, colorspace_in, colorspace_out):
    if colorspace_in.upper() == COLORSPACE_RGB:
        # [-1, 1] => [0, 1]
        img = (img + 1) / 2

        if colorspace_out == COLORSPACE_LAB:
            img = rgb_to_lab(img)

    elif colorspace_in.upper() == COLORSPACE_LAB:
        L_chan, a_chan, b_chan = tf.compat.v1unstack(img, axis=3)

        # L: [-1, 1] => [0, 100]
        # A, B: [-1, 1] => [-110, 110]
        img = tf.compat.v1stack([(L_chan + 1) / 2 * 100, a_chan * 110, b_chan * 110], axis=3)

        if colorspace_out == COLORSPACE_RGB:
            img = lab_to_rgb(img)

    return img


def rgb_to_lab(srgb):
    # based on https://github.com/torch/image/blob/9f65c30167b2048ecbe8b7befdc6b2d6d12baee9/generic/image.c
    with tf.compat.v1name_scope("rgb_to_lab"):
        srgb_pixels = tf.compat.v1reshape(srgb, [-1, 3])

        with tf.compat.v1name_scope("srgb_to_xyz"):
            linear_mask = tf.compat.v1cast(srgb_pixels <= 0.04045, dtype=tf.compat.v1float32)
            exponential_mask = tf.compat.v1cast(srgb_pixels > 0.04045, dtype=tf.compat.v1float32)
            rgb_pixels = (srgb_pixels / 12.92 * linear_mask) + (((srgb_pixels + 0.055) / 1.055) ** 2.4) * exponential_mask
            rgb_to_xyz = tf.compat.v1constant([
                #    X        Y          Z
                [0.412453, 0.212671, 0.019334],  # R
                [0.357580, 0.715160, 0.119193],  # G
                [0.180423, 0.072169, 0.950227],  # B
            ])
            xyz_pixels = tf.compat.v1matmul(rgb_pixels, rgb_to_xyz)

        # https://en.wikipedia.org/wiki/Lab_color_space#CIELAB-CIEXYZ_conversions
        with tf.compat.v1name_scope("xyz_to_cielab"):

            # normalize for D65 white point
            xyz_normalized_pixels = tf.compat.v1multiply(xyz_pixels, [1 / 0.950456, 1.0, 1 / 1.088754])

            epsilon = 6 / 29
            linear_mask = tf.compat.v1cast(xyz_normalized_pixels <= (epsilon**3), dtype=tf.compat.v1float32)
            exponential_mask = tf.compat.v1cast(xyz_normalized_pixels > (epsilon**3), dtype=tf.compat.v1float32)
            fxfyfz_pixels = (xyz_normalized_pixels / (3 * epsilon**2) + 4 / 29) * linear_mask + (xyz_normalized_pixels ** (1 / 3)) * exponential_mask

            # convert to lab
            fxfyfz_to_lab = tf.compat.v1constant([
                #  l       a       b
                [0.0, 500.0, 0.0],  # fx
                [116.0, -500.0, 200.0],  # fy
                [0.0, 0.0, -200.0],  # fz
            ])
            lab_pixels = tf.compat.v1matmul(fxfyfz_pixels, fxfyfz_to_lab) + tf.compat.v1constant([-16.0, 0.0, 0.0])

        return tf.compat.v1reshape(lab_pixels, tf.compat.v1shape(srgb))


def lab_to_rgb(lab):
    with tf.compat.v1name_scope("lab_to_rgb"):
        lab_pixels = tf.compat.v1reshape(lab, [-1, 3])

        # https://en.wikipedia.org/wiki/Lab_color_space#CIELAB-CIEXYZ_conversions
        with tf.compat.v1name_scope("cielab_to_xyz"):
            # convert to fxfyfz
            lab_to_fxfyfz = tf.compat.v1constant([
                #   fx      fy        fz
                [1 / 116.0, 1 / 116.0, 1 / 116.0],  # l
                [1 / 500.0, 0.0, 0.0],  # a
                [0.0, 0.0, -1 / 200.0],  # b
            ])
            fxfyfz_pixels = tf.compat.v1matmul(lab_pixels + tf.compat.v1constant([16.0, 0.0, 0.0]), lab_to_fxfyfz)

            # convert to xyz
            epsilon = 6 / 29
            linear_mask = tf.compat.v1cast(fxfyfz_pixels <= epsilon, dtype=tf.compat.v1float32)
            exponential_mask = tf.compat.v1cast(fxfyfz_pixels > epsilon, dtype=tf.compat.v1float32)
            xyz_pixels = (3 * epsilon**2 * (fxfyfz_pixels - 4 / 29)) * linear_mask + (fxfyfz_pixels ** 3) * exponential_mask

            # denormalize for D65 white point
            xyz_pixels = tf.compat.v1multiply(xyz_pixels, [0.950456, 1.0, 1.088754])

        with tf.compat.v1name_scope("xyz_to_srgb"):
            xyz_to_rgb = tf.compat.v1constant([
                #     r           g          b
                [3.2404542, -0.9692660, 0.0556434],  # x
                [-1.5371385, 1.8760108, -0.2040259],  # y
                [-0.4985314, 0.0415560, 1.0572252],  # z
            ])
            rgb_pixels = tf.compat.v1matmul(xyz_pixels, xyz_to_rgb)
            # avoid a slightly negative number messing up the conversion
            rgb_pixels = tf.compat.v1clip_by_value(rgb_pixels, 0.0, 1.0)
            linear_mask = tf.compat.v1cast(rgb_pixels <= 0.0031308, dtype=tf.compat.v1float32)
            exponential_mask = tf.compat.v1cast(rgb_pixels > 0.0031308, dtype=tf.compat.v1float32)
            srgb_pixels = (rgb_pixels * 12.92 * linear_mask) + ((rgb_pixels ** (1 / 2.4) * 1.055) - 0.055) * exponential_mask

        return tf.compat.v1reshape(srgb_pixels, tf.compat.v1shape(lab))
