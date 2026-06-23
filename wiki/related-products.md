# Related Products

This document summarizes existing photo culling and similar-photo management products relevant to Cullary.

## Aftershoot

**Positioning**

Aftershoot is an AI-assisted photography workflow product. It started around culling and has expanded toward editing and broader post-production automation.

**Relevant Features**

- AI photo culling.
- Similar/duplicate grouping.
- Blur and focus detection.
- Closed-eye and face-related checks.
- Batch workflow for professional photographers.
- Integration into editing/export workflows.

**Likely Technical Approach**

Public materials describe AI-based culling, but the exact algorithms are proprietary. Based on product behavior, it likely combines:

- visual similarity embeddings for grouping;
- face detection and face quality checks;
- blur/focus scoring;
- learned image quality or aesthetic models;
- workflow rules tuned for wedding/event photography.

## Narrative Select

**Positioning**

Narrative Select is a culling tool for photographers, especially high-volume shoots.

**Relevant Features**

- Fast RAW review.
- Scene-based grouping.
- Close-up face panels.
- Eye/focus warnings.
- Sharpness-based sorting within similar scenes.
- Lightroom-oriented workflow.

**Likely Technical Approach**

The product appears to rely on:

- RAW preview extraction for fast viewing;
- time/session grouping;
- image similarity grouping;
- face detection and face crops;
- sharpness/focus scoring around faces and subjects.

## FilterPixel

**Positioning**

FilterPixel is an AI culling tool aimed at wedding, event, portrait, and sports photographers.

**Relevant Features**

- Basic culling for blurry, bad, or duplicate photos.
- Deeper AI culling for expressions, moments, and action quality.
- Similar-photo grouping.
- Face and closed-eye detection.
- RAW format support, including Hasselblad `.3FR` according to its public format-support claims.

**Likely Technical Approach**

Its public feature set suggests:

- similarity embeddings for grouping;
- technical quality scoring;
- face and eye-state models;
- expression/moment classifiers;
- possibly learned ranking models for event photography.

## Excire Foto / Excire Search

**Positioning**

Excire is more photo-management/search oriented than pure culling. Excire Foto is standalone; Excire Search integrates with Lightroom Classic.

**Relevant Features**

- Local AI photo search.
- Similarity search.
- Duplicate search.
- Aesthetic assessment.
- Keyword/object/person-oriented organization.
- Local processing emphasis.

**Likely Technical Approach**

Excire likely uses:

- local computer vision embeddings;
- object/person classifiers;
- duplicate and near-duplicate similarity search;
- image aesthetics or quality scoring;
- metadata-aware catalog indexing.

## Adobe Lightroom Assisted Culling

**Positioning**

Lightroom is a full photo catalog and editing platform. Assisted culling adds AI support to the existing editing workflow.

**Relevant Features**

- AI-assisted selection of better images.
- Face-aware quality assessment.
- Rating/selection workflow integrated into Lightroom.
- Works inside the broader Adobe catalog/editing ecosystem.

**Likely Technical Approach**

Adobe has not fully exposed the algorithmic details, but the feature likely combines:

- learned image quality models;
- face detection and expression/eye checks;
- blur/focus assessment;
- catalog metadata;
- cloud/local Adobe AI infrastructure depending on product mode.

## Product Gap for Cullary

Existing products validate the demand, but many are optimized for professional delivery workflows, Lightroom integration, subscriptions, or broad catalog management.

Cullary can focus on a narrower gap:

- local/NAS-first archive cleanup;
- not a full editor;
- not a full DAM/catalog system;
- keep-first review by cluster;
- safe staging instead of destructive deletion;
- strong RAW preview extraction, especially for large camera files such as Hasselblad `.3FR`.
