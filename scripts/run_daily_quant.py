"""Usage: python scripts/run_daily_quant.py [--data-dir data] [--force-rebuild]."""
import argparse
import json
import logging
import os
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from modules.daily_quant import run_daily_quant, load_config


def main(argv=None):
    parser=argparse.ArgumentParser(description='Archive daily underlying research and separate Public option observations.')
    parser.add_argument('--config',type=Path)
    parser.add_argument('--data-dir',type=Path,default=Path(__file__).resolve().parents[1]/'data')
    parser.add_argument('--force-rebuild',action='store_true',help='Developer-only: preserve a backup and explicitly rebuild existing artifacts; disabled in Actions.')
    args=parser.parse_args(argv)
    # No HTTP bodies, account IDs, credentials or provider exception reprs in logs.
    logging.disable(logging.CRITICAL)
    try:
        report=run_daily_quant(root=args.data_dir,config=load_config(args.config),force=args.force_rebuild,
                               code_revision=os.environ.get('ALPHAOS_CODE_REVISION') or os.environ.get('GITHUB_SHA'))
        print(json.dumps(report,sort_keys=True))
        return 1 if report['status'] in ('failed','partial') else 0
    except Exception:
        print(json.dumps({'status':'failed','reason':'pipeline_configuration_or_storage_error'}))
        return 1


if __name__=='__main__':
    raise SystemExit(main())
