#!/bin/bash

bash setup/install.sh
streamlit run streamlit_app.py --server.port 8000
