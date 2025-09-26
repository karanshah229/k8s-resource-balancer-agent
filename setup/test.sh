#!/bin/bash

bash setup/install.sh
python3 -m pytest -v --junit-xml=unit.xml -n 5
