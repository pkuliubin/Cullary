# Cullary

Cullary is a local-first photo culling tool that clusters similar shots, recommends the best keepers, and safely moves the rest aside for review.

## Why

Camera workflows often produce many near-duplicate photos: burst shots, repeated portraits, bracketed scenes, and multiple attempts at the same composition. This is especially painful with large RAW files, NAS archives, and long-term photo libraries.

Cullary focuses on one job:

> Pick a folder, group similar photos, recommend 1-3 keepers per group, let the user confirm, then move the rest to a safe staging area.

## Product Principles

- Local-first: photos stay on the user's machine or NAS.
- Keep-first workflow: users confirm what to keep instead of manually selecting what to delete.
- Safe cleanup: non-keepers are moved to a staging folder, not permanently deleted.
- RAW-aware: large RAW files are preserved as the source of truth; previews or thumbnails are used for fast analysis.
- Offline batch processing: long processing time is acceptable if the results are reliable.

## Planned Workflow

1. Select a folder.
2. Scan photos and metadata.
3. Extract embedded previews or generate thumbnails.
4. Cluster near-duplicate photos using time, visual similarity, and optional GPS.
5. Recommend the best 1-3 candidates per cluster.
6. Review clusters in a task-focused UI.
7. Move rejected files to a `_to_delete/` staging folder.

## Documentation

- [Related Products](wiki/related-products.md)
- [Implementation Plan](wiki/implementation-plan.md)
