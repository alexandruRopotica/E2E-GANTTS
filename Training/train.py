import numpy as np
import tensorflow_addons as tfa
import tensorflow_hub as hub
import tensorflow_text as text
import tensorflow as tf
import librosa
import os

from Models.FeatureNet.cbhg import CBHG
from Models.GeneratorNet.generator import Generator
from Models.DiscriminatorNet.discriminator import Discriminator
from Models.bert import BERT

PREPROCESSOR = "https://tfhub.dev/tensorflow/bert_en_uncased_preprocess/3"
ENCODER = "https://tfhub.dev/tensorflow/small_bert/bert_en_uncased_L-12_H-256_A-4/1"
BERT_MODEL = BERT(PREPROCESSOR, ENCODER)
DISC_LEARNING_RATE = 1e-4
GEN_LEARNING_RATE = 5e-5
BETA_1 = 0
BETA_2 = 0.999
DECAY_RATE = 0.9999
WINDOWS = [240, 480, 960, 1920, 3600]
BATCH_SIZE = 1
EPOCHS = 1
TEXT_DIR = '/GANTTS/E2E-GANTTS/LJSpeech/texts'
WAVS_DIR = '/GANTTS/E2E-GANTTS/LJSpeech/wavs'


def getSamples(audio, windows):
    totalSamples = len(audio[0])
    subSamples = []
    for window in windows:
        idx = np.random.randint(0, totalSamples - window)
        subSamples.append(audio[:, idx:idx+window, :])
    return subSamples


def getDatasets(wavsDir, textDir):
    audioList, textList = [], []
    for wav in os.listdir(wavsDir):
        audio, _ = librosa.load(wavsDir + '/' + wav, sr=24000)
        duration = librosa.get_duration(audio, sr=24000)
        offset = np.random.randint(0, duration - 2)
        audio, _ = librosa.load(wavsDir + '/' + wav, sr=24000, offset=int(offset), duration=2)
        quantizedAudio = librosa.mu_compress(audio)
        quantizedAudio = tf.reshape(quantizedAudio[0:-1], (1, 48000, 1))
        audioList.append(quantizedAudio)
        textFile = wav.split('.')[0] + ".txt"
        content = ""
        with open(os.path.join(textDir, textFile), 'r+', encoding='utf-8') as f:
            content = f.read()
        textList.append(content)
    audioDataset = tf.concat(audioList, axis=0)
    textDataset = BERT_MODEL(textList)
    return audioDataset, textDataset
    


def initializeModels():
    featureNet = CBHG(BATCH_SIZE, 16, True)
    generator = Generator(BATCH_SIZE, True)
    discriminator = Discriminator()
    genOptimizer = tfa.optimizers.MovingAverage(decay=DECAY_RATE,
        optimizer=tf.keras.optimizers.Adam(lr=GEN_LEARNING_RATE, beta_1=BETA_1, beta_2=BETA_2))
    discOptimizer = tf.keras.optimizers.Adam(lr=DISC_LEARNING_RATE, beta_1=BETA_1, beta_2=BETA_2)
    return featureNet, generator, discriminator, genOptimizer, discOptimizer


def trainStep(audioBatch, text, featureNet, generator, discriminator, genOptimizer, discOptimizer):
    with tf.device('/device:GPU:0'):
        noise = tf.random.normal((BATCH_SIZE, 128, 1))
        with tf.GradientTape() as genTape, tf.GradientTape() as discTape, tf.GradientTape() as featureTape:
            genFeatures, discFeatures = featureNet(text)
            generatedAudio = generator(genFeatures, noise)
            w1, w2, w3, w4, w5 = getSamples(generatedAudio, WINDOWS)
            fakeAudio = discriminator(w1, w2, w3, w4, w5, discFeatures)
            w1, w2, w3, w4, w5 = getSamples(audioBatch, WINDOWS)
            realAudio = discriminator(w1, w2, w3, w4, w5, discFeatures)
            discFakeLoss = tf.losses.hinge(tf.zeros_like(fakeAudio), fakeAudio)
            discRealLoss = tf.losses.hinge(tf.ones_like(realAudio), realAudio)
            discLoss = discFakeLoss + discRealLoss
            genLoss = tf.losses.hinge(tf.ones_like(fakeAudio), fakeAudio)
        discGradients = discTape.gradient(discLoss, discriminator.trainable_variables)
        discOptimizer.apply_gradients(zip(discGradients, discriminator.trainable_variables))
        genGradients = genTape.gradient(genLoss, generator.trainable_variables)
        genOptimizer.apply_gradients(zip(genGradients, generator.trainable_variables))
        featureGradients = featureTape.gradient(discLoss, featureNet.trainable_variables)
        discOptimizer.apply_gradients(zip(featureGradients, featureNet.trainable_variables))
        print("Generator loss:", genLoss.numpy(),"| Discriminator loss:", discLoss.numpy())


def train(audioDataset, textDataset, epochs):
    featureNet, generator, discriminator, genOptimizer, discOptimizer = initializeModels()
    for epoch in range(epochs):
        print("Epoch", epoch+1)
        for audio, text in zip(audioDataset, textDataset):
            audio = tf.expand_dims(audio, axis=0)
            text = tf.expand_dims(text, axis=0)
            trainStep(audio, text, featureNet, generator, discriminator, genOptimizer, discOptimizer)


if __name__ == '__main__':
    audioDataset, textDataset = getDatasets(WAVS_DIR, TEXT_DIR)
    print("Processed audio and texts")
    train(audioDataset, textDataset, EPOCHS)
