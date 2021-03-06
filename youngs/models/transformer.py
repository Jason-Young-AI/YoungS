#!/usr/bin/env python3 -u
# -*- coding: utf-8 -*-
#
# Copyright (c) Jason Young (杨郑鑫).
#
# E-Mail: <AI.Jason.Young@outlook.com>
# 2020-03-31 22:05
#
# This source code is licensed under the Apache-2.0 license found in the
# LICENSE file in the root directory of this source tree.


import torch

from youngs.models import register_model, Model

from youngs.modules.encoders import TransformerEncoder
from youngs.modules.decoders import TransformerDecoder
from youngs.modules.perceptrons import MultilayerPerceptron

from youngs.utilities.extractor import get_padding_mask, get_foresee_mask


@register_model('transformer')
class Transformer(Model):
    def __init__(self, settings, dimension, encoder, decoder, generator):
        super(Transformer, self).__init__(settings)
        assert dimension == encoder.dimension
        assert dimension == decoder.dimension
        self.dimension = dimension
        self.encoder = encoder
        self.decoder = decoder
        self.generator = generator

    def forward(self, source, target):
        source_mask = self.get_source_mask(source)
        target_mask = self.get_target_mask(target)

        codes = self.encoder(source, source_mask)

        hidden, cross_attention_weight = self.decoder(target, codes, target_mask, source_mask)

        logits = self.generator(hidden)

        return logits, cross_attention_weight

    def get_source_mask(self, source):
        source_pad_index = self.encoder.embed_token.padding_idx
        source_mask = get_padding_mask(source, source_pad_index).unsqueeze(1)
        return source_mask

    def get_target_mask(self, target):
        target_pad_index = self.decoder.embed_token.padding_idx
        target_mask = get_padding_mask(target, target_pad_index).unsqueeze(1)
        foresee_mask = get_foresee_mask(
            target.size(-1), target.size(-1),
            target.device,
        ).unsqueeze(0)
        target_mask = target_mask | foresee_mask
        return target_mask

    @classmethod
    def setup(cls, settings, factory):
        args = settings.args
        encoder = TransformerEncoder(
            factory.vocabularies['source'],
            args.encoder.layer_number,
            args.encoder.dimension,
            args.encoder.feedforward_dimension,
            args.encoder.head_number,
            args.encoder.dropout_probability,
            args.encoder.attention_dropout_probability,
            args.encoder.feedforward_dropout_probability,
            args.encoder.normalize_position
        )
        decoder = TransformerDecoder(
            factory.vocabularies['target'],
            args.decoder.layer_number,
            args.decoder.dimension,
            args.decoder.feedforward_dimension,
            args.decoder.head_number,
            args.decoder.dropout_probability,
            args.decoder.attention_dropout_probability,
            args.decoder.feedforward_dropout_probability,
            args.decoder.normalize_position
        )

        generator = MultilayerPerceptron(decoder.dimension, len(factory.vocabularies['target']), False)
        torch.nn.init.normal_(generator.linear_layers[0].weight, mean=0, std=decoder.dimension ** -0.5)

        if args.share_enc_dec_embeddings:
            decoder.embed_token.weight = encoder.embed_token.weight

        if args.share_dec_io_embeddings:
            generator.linear_layers[0].weight = decoder.embed_token.weight

        model = cls(settings, args.dimension, encoder, decoder, generator)

        return model

    def personalized_load_state(self, model_state):
        self.load_state_dict(model_state, strict=False)
