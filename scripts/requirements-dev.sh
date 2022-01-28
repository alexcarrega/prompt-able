#!/bin/bash

# Copyright (c) 2020-2029 Alex Carrega <contact@alexcarrega.com>
# author: Alex Carrega <contact@alexcarrega.com>

pipenv lock -r --dev-only > dev/requirements.txt
