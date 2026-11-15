"""Enterprise operator entry point for the opt-in FHE training prototype."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from experiments.he_training.cli import main

if __name__=='__main__':main()
