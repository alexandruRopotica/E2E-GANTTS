import os
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3' 
os.environ['CUDA_VISIBLE_DEVICES'] = '-1'
import tensorflow as tf
tf.compat.v1.logging.set_verbosity(tf.compat.v1.logging.ERROR)
from transformers import logging
logging.set_verbosity_error()
from Models.bert import BERT
from Models.FeatureNet.cbhg import CBHG
from Models.GeneratorNet.generator import Generator
from Models.DiscriminatorNet.discriminator import Discriminator
import numpy as np
import soundfile as sf
from Training.train import getDataset


TEXT_DIR = './LJspeechTest/texts'
WAVS_DIR = './LJspeechTest/wavs'
GENERATED_WAVS_DIR = './LJspeechTest/generatedWavs'
BATCH_SIZE = 10
CKPT_DIR = './Checkpoints/'


def FrechetInceptionDistance(realAudio, generatedAudio):
    inceptionv3 = tf.keras.applications.InceptionV3(include_top=False, input_shape=(128,125,3), pooling='avg')
    realFeatures = inceptionv3(realAudio)
    generatedFeatures = inceptionv3(generatedAudio)
    muReal, sigmaReal = np.mean(realFeatures), np.cov(realFeatures, rowvar=False)
    muGenerated, sigmaGenerated = np.mean(generatedFeatures), np.cov(generatedFeatures, rowvar=False)
    muDiff = np.linalg.norm(muReal- muGenerated)
    covDiff = sigmaReal + sigmaGenerated - 2*(tf.math.sqrt(sigmaReal*sigmaGenerated))
    fid = muDiff**2 + np.trace(covDiff)
    return fid


def saveGeneratedAudio(textDataset, checkpointDir):
    featureNet = CBHG(BATCH_SIZE, 16, True, 768)
    initFNetTensor = tf.random.normal((BATCH_SIZE, 768, 1))
    initFNet = featureNet(initFNetTensor)
    featureNet.load_weights(os.path.join(CKPT_DIR, "fnet.keras"))
    embeddings = featureNet(textDataset)
    generator = Generator(BATCH_SIZE, True)
    initGenTensor = tf.random.normal((BATCH_SIZE, 400, 768))
    noise = tf.random.normal((BATCH_SIZE, 128, 1))
    initGen = generator(initGenTensor, noise)
    generator.load_weights(os.path.join(CKPT_DIR, "gen.keras"))
    generatedAudio = generator(embeddings)
    for i in range(len(generatedAudio)):
        generatedAudio[i] = tf.reshape(generatedAudio[i], (48000))
        sf.write(os.path.join(GENERATED_WAVS_DIR, "generatedWav"+str(i)), generatedAudio[i], 24000)


if __name__=='__main__':
    audioDataset, textDataset = getDataset(WAVS_DIR, TEXT_DIR)
    saveGeneratedAudio(textDataset)