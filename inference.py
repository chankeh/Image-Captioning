import torch
import torch.nn.functional as F
import numpy as np
import json
import torchvision.transforms as transforms
import matplotlib.pyplot as plt
import matplotlib.cm as cm
import skimage.transform
import argparse
# from scipy.misc import imread, imresize
from imageio import imread
from PIL import Image

device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

'''
read an image and caption it with beam search

input param:
    encoder: encoder model
    decoder: decoder model
    image_path: path to image
    word_map: word map
    beam_size: number of sequences to consider at each decode-step
return: 
    seq: caption
    alphas: weights for visualization
''' 
def generate_caption(encoder, decoder, image_path, word_map, caption_model, beam_size = 3):

    # Read image and process
    img = imread(image_path)
    if len(img.shape) == 2:
        img = img[:, :, np.newaxis]
        img = np.concatenate([img, img, img], axis = 2)
    # img = imresize(img, (256, 256))
    img = np.array(Image.fromarray(img).resize((256, 256)))
    img = img.transpose(2, 0, 1)
    img = img / 255.
    img = torch.FloatTensor(img).to(device)
    normalize = transforms.Normalize(
                    mean = [0.485, 0.456, 0.406],
                    std = [0.229, 0.224, 0.225]
                )
    transform = transforms.Compose([normalize])
    image = transform(img)  # (3, 256, 256)

    # encode
    image = image.unsqueeze(0)  # (1, 3, 256, 256)
    encoder_out = encoder(image)  # (1, enc_image_size, enc_image_size, encoder_dim)
 
    # prediction (beam search)
    if caption_model == 'show_tell':
        seq = decoder.beam_search(encoder_out, beam_size, word_map)
        return seq
    elif caption_model == 'att2all':
        seq, alphas = decoder.beam_search(encoder_out, beam_size, word_map)
        return seq, alphas
    elif caption_model == 'adaptive_att' or caption_model == 'spatial_att':
        seq, alphas, betas = decoder.beam_search(encoder_out, beam_size, word_map)
        return seq, alphas, betas



'''
visualizes caption with weights at every word
adapted from: https://github.com/kelvinxu/arctic-captions/blob/master/alpha_visualization.ipynb

input param:
    image_path: path to image that has been captioned
    seq: caption
    alphas: attention weights
    betas: sentinel gate (only in adaptive attention)
    rev_word_map: reverse word mapping, i.e. ix2word
    smooth: smooth weights?
'''
def visualize_att(image_path, seq, alphas, rev_word_map, betas = None, smooth = True):

    image = Image.open(image_path)
    image = image.resize([14 * 24, 14 * 24], Image.LANCZOS)

    words = [rev_word_map[ind] for ind in seq]

    for t in range(len(words)):
        if t > 50:
            break
        plt.subplot(np.ceil(len(words) / 5.), 5, t + 1)

        plt.text(0, 1, '%s' % (words[t]), color = 'black', backgroundcolor = 'white', fontsize = 12)
        if betas is not None:
            plt.text(10, -120, '%.2f' % (1 - (betas[t].item())), color = 'green', backgroundcolor = 'white', fontsize = 15)
        
        plt.imshow(image)
        
        current_alpha = alphas[t, :]
        if smooth:
            alpha = skimage.transform.pyramid_expand(current_alpha.numpy(), upscale = 24, sigma = 8)
        else:
            alpha = skimage.transform.resize(current_alpha.numpy(), [14 * 24, 14 * 24])
        
        if t == 0:
            plt.imshow(alpha, alpha = 0)
        else:
            plt.imshow(alpha, alpha = 0.8)
        
        plt.set_cmap(cm.Greys_r)
        plt.axis('off')
    
    plt.show()


if __name__ == '__main__':

    model_path = 'models/best_checkpoint_test1.pth.tar'
    img = 'flickr8k/images/218342358_1755a9cce1.jpg'
    wordmap_path = 'flickr8k/output/wordmap_test1.json'
    beam_size = 5
    ifsmooth = False

    # load model
    checkpoint = torch.load(model_path, map_location = str(device))

    decoder = checkpoint['decoder']
    decoder = decoder.to(device)
    decoder.eval()

    encoder = checkpoint['encoder']
    encoder = encoder.to(device)
    encoder.eval()

    caption_model = checkpoint['config'].caption_model

    # Load word map (word2ix)
    with open(wordmap_path, 'r') as j:
        word_map = json.load(j)
    rev_word_map = {v: k for k, v in word_map.items()}  # ix2word

    # encoder-decoder with beam search
    if caption_model == 'show_tell':
        seq = generate_caption(encoder, decoder, img, word_map, caption_model, beam_size)
        caption = [rev_word_map[ind] for ind in seq if ind not in {word_map['<start>'], word_map['<end>'], word_map['<pad>']}]
        print('Caption: ', ' '.join(caption))

    elif caption_model == 'att2all':
        seq, alphas = generate_caption(encoder, decoder, img, word_map, caption_model, beam_size)
        alphas = torch.FloatTensor(alphas)
        # visualize caption and attention of best sequence
        visualize_att(
            image_path = img,
            seq = seq,
            rev_word_map = rev_word_map, 
            alphas = alphas, 
            smooth = ifsmooth
        )

    elif caption_model == 'adaptive_att' or caption_model == 'spatial_att':
        seq, alphas, betas = generate_caption(encoder, decoder, img, word_map, caption_model, beam_size)
        alphas = torch.FloatTensor(alphas)
        visualize_att(
            image_path = img, 
            seq = seq,
            rev_word_map = rev_word_map,
            alphas = alphas,
            betas = betas,
            smooth = ifsmooth
        )