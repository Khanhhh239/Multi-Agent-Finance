"""Nạp mã nguồn cục bộ và giới hạn CPU cho toàn bộ bộ kiểm thử."""
import os
import sys
from pathlib import Path
os.environ.setdefault('AGENT1_THREADS', '4')
os.environ.setdefault('OMP_NUM_THREADS', '4')
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
