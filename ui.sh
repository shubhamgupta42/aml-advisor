#!/usr/bin/env bash
cd "$(dirname "$0")"
exec streamlit run src/ui/app.py
