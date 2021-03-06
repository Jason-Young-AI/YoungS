#!/usr/bin/env python3 -u
# -*- coding: utf-8 -*-
#
# Copyright (c) Jason Young (杨郑鑫).
#
# E-Mail: <AI.Jason.Young@outlook.com>
# 2020-04-02 08:23
#
# This source code is licensed under the Apache-2.0 license found in the
# LICENSE file in the root directory of this source tree.


from yoolkit.logging import setup_logger, logging_level
from yoolkit.registration import import_modules

import youngs.hocon.arguments as harg

from youngs.factories import build_factory

from youngs.utilities.random import fix_random_procedure


def preprocess(args):
    import_modules(args.user_defined_modules_directory, 'youngs.user_defined')
    logger = setup_logger(args.logger.name, logging_path=args.logger.path, logging_level=logging_level['INFO'], to_console=args.logger.console_report, clean_logging_file=True)

    logger.disabled = args.logger.off

    fix_random_procedure(args.random_seed)

    logger.info(
        f'\n The following is the arguments:'
        f'\n{args}'
    )

    logger.info(f' + Building Factory ...')
    factory = build_factory(args.factory, logger)
    logger.info(f'   The construction of Factory [\'{args.factory.name}\' : \'{factory.__class__.__name__}\'] is complete.')

    logger.info(f' + Building Ancillary Datasets ...')
    factory.build_ancillary_datasets(args.factory.args)
    logger.info(f'   The construction of Ancillary Datasets is complete.')

    logger.info(f' + Building Datasets ...')
    factory.build_datasets(args.factory.args)
    logger.info(f'   The construction of Datasets is complete.')

    logger.info(f' $ Finished !')


def main():
    preprocess_args = harg.get_arguments('preprocess')
    preprocess(preprocess_args)


if __name__ == '__main__':
    main()
