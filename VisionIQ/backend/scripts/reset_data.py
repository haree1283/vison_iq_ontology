#!/usr/bin/env python3
"""Start VisionIQ empty: delete every vehicle record from the VisionIQ database and hide all videos processed
before now, so only videos uploaded / live sessions recorded from now on appear (dashboards, ontology, library).

Nothing on disk is deleted -- the NH5 Library folders (webapp_data) stay as they are. User accounts are kept.

  python backend/scripts/reset_data.py            # asks for confirmation
  python backend/scripts/reset_data.py --yes
  python backend/scripts/reset_data.py --show-all # undo the cutoff: show every Library video again
"""
import argparse
import sys
from datetime import datetime
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(BACKEND_DIR / '.env')

from config.database import db, initialize_database, set_setting  # noqa: E402
from services.nh5_bridge import IMPORT_SINCE_SETTING  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--yes', action='store_true', help='do not ask for confirmation')
    ap.add_argument('--show-all', action='store_true', help='remove the cutoff instead (old videos are re-imported)')
    args = ap.parse_args()
    status = initialize_database()

    if args.show_all:
        db.execute('DELETE FROM app_settings WHERE name = %s', (IMPORT_SINCE_SETTING,))
        print('Cutoff removed: every NH5 Library video is imported again on the next server start / sync.')
        return

    count = db.query('SELECT COUNT(*) AS c FROM vehicle_events')[0]['c']
    if not args.yes:
        answer = input(f'Delete {count} vehicle records from the {status["engine"]} database and hide videos '
                       f'processed before now? [y/N] ')
        if answer.strip().lower() != 'y':
            print('Cancelled.')
            return
    since = datetime.now().isoformat(timespec='seconds')
    db.execute('DELETE FROM vehicle_events')
    db.execute('DELETE FROM nh5_imports')
    set_setting(IMPORT_SINCE_SETTING, since)
    print(f'Deleted {count} vehicle records. Only videos uploaded from {since.replace("T", " ")} on are shown.')


if __name__ == '__main__':
    main()
