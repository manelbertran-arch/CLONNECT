#!/bin/bash
set -e

echo "Building frontend..."
cd "$(dirname "$0")/../frontend"
rm -rf dist node_modules/.cache
npm run build

echo "Copying to backend/static..."
rm -rf ../backend/static/*
cp -r dist/* ../backend/static/

echo "Frontend build complete"
cd ..

echo "Committing and pushing..."
git add backend/static/
git commit -m "build: update frontend bundle" --allow-empty
git push

echo "Deploy triggered!"
