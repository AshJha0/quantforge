# ADR: C++26 feature detection

## Status
Accepted

## Decision
Target C++26, but detect compiler and standard-library support for individual features. Maintain a documented supported-toolchain matrix.

## Consequences
Do not assume all C++26 facilities are available in every compiler. Provide a minimal portable baseline and guarded optional features.
