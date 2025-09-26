#!/bin/bash

bash setup/install.sh
streamlit run app.py --server.port 8000
