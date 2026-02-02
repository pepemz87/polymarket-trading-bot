"""
Script to run the Streamlit dashboard.
"""
import os
import sys

# Add src to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

if __name__ == "__main__":
    os.system("streamlit run src/dashboard/streamlit_app.py")
