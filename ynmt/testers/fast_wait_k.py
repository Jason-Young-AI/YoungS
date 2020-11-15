#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
# Copyright (c) Jason Young (杨郑鑫).
#
# E-Mail: <AI.Jason.Young@outlook.com>
# 2020-06-29 18:33
#
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.


import torch

from ynmt.testers import register_tester, Tester
from ynmt.testers.ancillaries import GreedySearcher

from ynmt.data.batch import Batch
from ynmt.data.instance import Instance
from ynmt.data.iterator import RawTextIterator
from ynmt.data.attribute import pad_attribute

from ynmt.utilities.metrics import BLEUScorer
from ynmt.utilities.sequence import stringize, numericalize, tokenize
from ynmt.utilities.extractor import get_tiled_tensor


@register_tester('fast_wait_k')
class FastWaitK(Tester):
    def __init__(self,
        task, output_names,
        searcher, bpe_symbol, remove_bpe,
        source_path, target_path,
        batch_size, batch_type,
        wait_source_time,
        device_descriptor, logger
    ):
        super(FastWaitK, self).__init__(task, output_names, device_descriptor, logger)
        self.searcher = searcher
        self.bpe_symbol = bpe_symbol
        self.remove_bpe = remove_bpe

        self.source_path = source_path
        self.target_path = target_path
        self.batch_size = batch_size
        self.batch_type = batch_type
        self.wait_source_time = wait_source_time

    def initialize(self):
        self.total_sentence_number = 0

    @classmethod
    def setup(cls, args, task, device_descriptor, logger):
        searcher = GreedySearcher(
            search_space_size = len(task.vocabularies['target']),
            initial_node = task.vocabularies['target'].bos_index,
            terminal_node = task.vocabularies['target'].eos_index,
            min_depth = args.searcher.min_length, max_depth = args.searcher.max_length,
        )

        output_names = ['trans', 'trans-detailed']

        fast_wait_k = cls(
            task, output_names,
            searcher, args.bpe_symbol, args.remove_bpe,
            args.source, args.target,
            args.batch_size, args.batch_type,
            args.wait_source_time,
            device_descriptor, logger
        )

        return fast_wait_k

    def test(self, model, batch):
        source = batch.source
        parallel_line_number, _ = source.size()

        self.searcher.initialize(parallel_line_number, self.device_descriptor)

        while not self.searcher.finished:
            temp_source = torch.index_select(source, 0, self.searcher.line_original_indices)
            source_mask = model.get_source_mask(temp_source)
            codes = model.encoder(temp_source, source_mask)

            previous_prediction = self.searcher.found_nodes
            previous_prediction_mask = model.get_target_mask(previous_prediction)
            cross_mask = model.get_cross_mask(temp_source, previous_prediction, self.wait_source_time)

            hidden, cross_attention_weight = model.decoder(
                previous_prediction,
                codes,
                previous_prediction_mask,
                cross_mask
            )

            logits = model.generator(hidden)
            log_probs = torch.nn.functional.log_softmax(logits, dim=-1)
            prediction_distribution = log_probs[:, -1, :]
            self.searcher.search(prediction_distribution)

            self.searcher.update()

    def input(self):
        def instance_handler(lines):
            (source_line, ) = lines
            instance = Instance(set({'source', }))
            instance['source'] = numericalize(tokenize(source_line), self.task.vocabularies['source'])
            return instance

        def instance_size_calculator(instances):
            self.max_source_length = 0
            if self.batch_type == 'sentence':
                batch_size = len(instances)

            if self.batch_type == 'token':
                if len(instances) == 1:
                    self.max_source_length = 0

                self.max_source_length = max(self.max_source_length, len(instances[-1].source))

                batch_size = len(instances) * self.max_source_length

            return batch_size
 
        input_iterator = RawTextIterator(
            [self.source_path, ],
            instance_handler,
            self.batch_size,
            instance_size_calculator = instance_size_calculator
        )

        for batch in input_iterator:
            padded_batch = Batch(set({'source', }))
            padded_attributes, _ = pad_attribute(batch.source, self.task.vocabularies['source'].pad_index)
            padded_batch.source = torch.tensor(padded_attributes, dtype=torch.long, device=self.device_descriptor)
            yield padded_batch

    def output(self, output_basepath):
        results = self.searcher.results

        with open(output_basepath + '.' + 'trans', 'a', encoding='utf-8') as translation_file,\
            open(output_basepath + '.' + 'trans-detailed', 'a', encoding='utf-8') as detailed_translation_file:
            for result in results:
                detailed_translation_file.writelines(f'No.{self.total_sentence_number}:\n')
                self.total_sentence_number += 1
                log_prob = result['log_prob']
                prediction = result['path']
                detailed_translation_file.writelines(f'log_prob={log_prob:.3f}\n')
                tokens = stringize(prediction, self.task.vocabularies['target'])
                sentence = ' '.join(tokens)
                if self.remove_bpe:
                    sentence = (sentence + ' ').replace(self.bpe_symbol, '').strip()
                detailed_translation_file.writelines(sentence + '\n')
                translation_file.writelines(sentence + '\n')
                detailed_translation_file.writelines(f'===================================\n')

    def report(self, output_basepath):
        if self.target_path is None:
            return

        bleu_scorer = BLEUScorer()
        with open(output_basepath + '.' + 'trans', 'r', encoding='utf-8') as translation_file, open(self.target_path, 'r', encoding='utf-8') as reference_file:
            for tra, ref in zip(translation_file, reference_file):
                bleu_scorer.add(tra.split(), [ref.split(), ])

        self.logger.info(bleu_scorer.result_string)

        with open(output_basepath + '.' + 'trans-detailed', 'a', encoding='utf-8') as detailed_translation_file:
            detailed_translation_file.writelines(bleu_scorer.result_string)
