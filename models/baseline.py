# -*- encoding: utf-8 -*-
'''
@File    :   baseline.py    
@Contact :   whut.hexin@foxmail.com
@License :   (C)Copyright 2017-2020, HeXin

@Modify Time      @Author    @Version    @Desciption
------------      -------    --------    -----------
2019/11/6 18:14   xin      1.0         None
'''

import torch
from torch import nn

from .backbones.resnet import ResNet
from .backbones.resnet_ibn_a import resnet50_ibn_a
from .backbones.resnext_ibn_a import resnext101_ibn_a
from .layers.pooling import GeM,GlobalConcatPool2d,GlobalAttnPool2d,GlobalAvgAttnPool2d,GlobalMaxAttnPool2d,GlobalConcatAttnPool2d

def weights_init_kaiming(m):
    classname = m.__class__.__name__
    if classname.find('Linear') != -1:
        nn.init.kaiming_normal_(m.weight, a=0, mode='fan_out')
        nn.init.constant_(m.bias, 0.0)
    elif classname.find('Conv') != -1:
        nn.init.kaiming_normal_(m.weight, a=0, mode='fan_in')
        if m.bias is not None:
            nn.init.constant_(m.bias, 0.0)
    elif classname.find('BatchNorm') != -1:
        if m.affine:
            nn.init.constant_(m.weight, 1.0)
            nn.init.constant_(m.bias, 0.0)


def weights_init_classifier(m):
    classname = m.__class__.__name__
    if classname.find('Linear') != -1:
        nn.init.normal_(m.weight, std=0.001)
        if m.bias:
            nn.init.constant_(m.bias, 0.0)


class Baseline(nn.Module):
    in_planes = 2048

    def __init__(self, num_classes, last_stride, model_path, backbone="resnet50", pool_type='avg', use_dropout=True):
        super(Baseline, self).__init__()
        if backbone == "resnet50":
            self.base = ResNet(last_stride)
        elif backbone == "resnet50_ibn_a":
            self.base = resnet50_ibn_a(last_stride)
        else:
            self.base = eval(backbone)(last_stride=last_stride)
        self.base.load_param(model_path)
        
        in_features = self.in_planes
        if pool_type == "avg":
            self.gap = nn.AdaptiveAvgPool2d(1)
        elif "gem" in pool_type:
            if pool_type !='gem':
                p = pool_type.split('_')[-1]
                p = float(p)
                self.gap = GeM(p=p, eps=1e-6, freeze_p=True)
            else:
                self.gap = GeM(eps=1e-6, freeze_p=False)
        elif pool_type == 'max':
            self.gap = nn.AdaptiveMaxPool2d(1)
        elif 'Att' in pool_type:
            self.gap = eval(pool_type)(in_features = in_features)
            in_features = self.gap.out_features(in_features)
        else:
            self.gap = eval(pool_type)()
            in_features = self.gap.out_features(in_features)

        self.num_classes = num_classes

        self.bottleneck = nn.BatchNorm1d(in_features)
        self.bottleneck.bias.requires_grad_(False)  # no shift
        self.classifier = nn.Linear(in_features, self.num_classes, bias=False)

        self.bottleneck.apply(weights_init_kaiming)
        self.classifier.apply(weights_init_classifier)
        # self.dropout = torch.nn.Dropout()
        self.use_dropout = use_dropout
    
        # if self.dropout >= 0:
        if use_dropout:
            self.dropout = nn.Dropout(self.dropout)
    def load_param(self, trained_path):
        param_dict = torch.load(trained_path)
        for i in param_dict:
            if 'classifier' in i:
                continue
            self.state_dict()[i].copy_(param_dict[i])
    def forward(self, x):
        global_feat = self.gap(self.base(x))  # (b, 2048, 1, 1)
        global_feat = global_feat.view(global_feat.shape[0], -1)  # flatten to (bs, 2048)
        feat = self.bottleneck(global_feat)  # normalize for angular softmax
        if self.training:
            if self.use_dropout:
                feat = self.dropout(feat)
            cls_score = self.classifier(feat)
            return cls_score, global_feat  # global feature for triplet loss
        else:
            return feat

    # def forward(self, x,output_feature=None):
    #     global_feat = self.gap(self.base(x))  # (b, 2048, 1, 1)
    #     global_feat = global_feat.view(global_feat.shape[0], -1)  # flatten to (bs, 2048)
    #     feat = self.bottleneck(global_feat)  # normalize for angular softmax
    #     if self.training:
    #         # [update] support exemplar trainer
    #         if output_feature == 'exemplar_feat':
    #             exemplar_feat = F.normalize(feat)
    #             if self.use_dropout:
    #                 exemplar_feat = self.dropout(exemplar_feat)
    #             return exemplar_feat

    #         if self.use_dropout:
    #             feat = self.dropout(feat)


    #         cls_score = self.classifier(feat)

    #         return cls_score, global_feat  # global feature for triplet loss
    #     else:
    #         return feat