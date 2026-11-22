"""Home page layout: headings wrap at word boundaries, buttons fill their card and line up at the bottom.
CSS only."""
import streamlit as st

HOME_FIX_CSS = """
.stApp div[data-testid="stColumn"] div[data-testid="stVerticalBlock"] {
  display: flex !important; flex-direction: column !important; height: 100% !important;
}
.stApp div[data-testid="stColumn"] h2 {
  font-size: 1.45rem !important; line-height: 1.15 !important;
  word-break: normal !important; overflow-wrap: normal !important; hyphens: none !important;
}
.stApp div[data-testid="stColumn"] div[data-testid="stElementContainer"]:has(button) {
  margin-top: auto !important; width: 100% !important;
}
.stApp div[data-testid="stColumn"] div[data-testid="stButton"],
.stApp div[data-testid="stColumn"] div[data-testid="stButton"] button {
  width: 100% !important; max-width: 100% !important; box-sizing: border-box !important;
}
.stApp div[data-testid="stColumn"] button {
  white-space: normal !important; padding: 10px 14px !important;
  justify-content: center !important; min-height: 44px !important;
}
.stApp div[data-testid="stColumn"] button p {
  white-space: normal !important; font-size: 0.98rem !important; line-height: 1.2 !important;
  margin: 0 !important; text-align: center !important;
}
"""


def inject_home_fix():
    st.markdown("<style>" + HOME_FIX_CSS + "</style>", unsafe_allow_html=True)
