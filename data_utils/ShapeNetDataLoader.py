# *_*coding:utf-8 *_*
import os
import json
import warnings
import numpy as np
import gc
from tqdm import tqdm
import h5py
from torch.utils.data import Dataset
warnings.filterwarnings('ignore')
import sys
sys.path.append('.')
from colors import *

def pc_normalize(pc):
    centroid = np.mean(pc, axis=0)
    pc = pc - centroid
    m = np.max(np.sqrt(np.sum(pc ** 2, axis=1)))
    pc = pc / m
    return pc

def jitter_point_cloud(batch_data, sigma=0.01, clip=0.05):
    """ Randomly jitter points. jittering is per point.
        Input:
          BxNx3 array, original batch of point clouds
        Return:
          BxNx3 array, jittered batch of point clouds
    """
    N, C = batch_data.shape
    assert(clip > 0)
    jittered_data = np.clip(sigma * np.random.randn(N, C), -1*clip, clip)
    jittered_data += batch_data
    return jittered_data

class PartNormalDataset(Dataset):
    def __init__(self, root, cache = {},npoints=2500, split='train', normalize=True, jitter=False):
        self.npoints = npoints
        self.root = root
        self.category = {}
        self.normalize = normalize
        self.jitter = jitter
        self.cache = cache

        self.wordnet_id_to_category = {}
        with open(os.path.join(self.root, 'synsetoffset2category.txt'), 'r') as f:
            for line in f:
                line = line.strip().split()
                self.category[line[0]] = line[1]
                self.wordnet_id_to_category[line[1]] = line[0]

        fn_split = os.path.join(self.root, 'train_test_split')
        with open(os.path.join(fn_split,'shuffled_train_file_list.json'), 'r') as f:
            train_ids = set([str(d.split('/')[2]) for d in json.load(f)])
        with open(os.path.join(fn_split,'shuffled_val_file_list.json'), 'r') as f:
            val_ids = set([str(d.split('/')[2]) for d in json.load(f)])
        with open(os.path.join(fn_split,'shuffled_test_file_list.json'), 'r') as f:
            test_ids = set([str(d.split('/')[2]) for d in json.load(f)])
            
        self.meta = {}
        for item in self.category:
            self.meta[item] = []
            dir_point = os.path.join(self.root, self.category[item])
            fns = sorted(os.listdir(dir_point))

            if split == 'trainval':
                fns = [fn for fn in fns if ((fn[0:-4] in train_ids) or (fn[0:-4] in val_ids))]
            elif split == 'train':
                fns = [fn for fn in fns if fn[0:-4] in train_ids]
            elif split == 'val':
                fns = [fn for fn in fns if fn[0:-4] in val_ids]
            elif split == 'test':
                fns = [fn for fn in fns if fn[0:-4] in test_ids]
            else:
                raise ValueError('Unknown split: %s. Exiting..' % (split))

            for fn in fns:
                self.meta[item].append(os.path.join(dir_point, fn))

        self.datapath = []
        for item in self.category:
            for fn in self.meta[item]:
                self.datapath.append(fn)

        self.classes = dict(zip(self.category, range(len(self.category))))
        print_kv('classes',self.classes.keys())

        self.seg_classes = {'Earphone': [16, 17, 18], 'Motorbike': [30, 31, 32, 33, 34, 35], 'Rocket': [41, 42, 43],
                            'Car': [8, 9, 10, 11], 'Laptop': [28, 29], 'Cap': [6, 7], 'Skateboard': [44, 45, 46],
                            'Mug': [36, 37], 'Guitar': [19, 20, 21], 'Bag': [4, 5], 'Lamp': [24, 25, 26, 27],
                            'Table': [47, 48, 49], 'Airplane': [0, 1, 2, 3], 'Pistol': [38, 39, 40],
                            'Chair': [12, 13, 14, 15], 'Knife': [22, 23]}

    def __getitem__(self, index):
        fn_full = self.datapath[index]
        parts = fn_full.split('/')
        wordnet_id = parts[-2]
        category = self.wordnet_id_to_category[wordnet_id]
        cls_id = np.array([self.classes[category]]).astype(np.int32)
        token = parts[-1].split('.')[0]
        h5_index = '%s_%s'%(wordnet_id,token)

        if h5_index in self.cache.keys():
            data = self.cache[h5_index]
            point_set = data[:, 0:3]
            normal = data[:, 3:6]
            seg = data[:, -1].astype(np.int32)
        else:
            print_err('Error: cache miss',h5_index)
            data = np.loadtxt(fn_full).astype(np.float32)

        if self.normalize:
            point_set = pc_normalize(point_set)

        if self.jitter:
            jitter_point_cloud(point_set)

        choice = np.random.choice(len(seg), self.npoints, replace=True)

        # resample
        point_set = point_set[choice, :]
        seg = seg[choice]
        normal = normal[choice, :]
        return point_set,cls_id, seg, normal

    def __len__(self):
        return len(self.datapath)