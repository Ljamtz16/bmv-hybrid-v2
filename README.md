# BMV Hybrid Research Portfolio

## Resumen (ES)
Repositorio academico con un sistema hibrido de trading cuantitativo y componentes de despliegue en edge (RPi). El foco principal es BMV Hybrid V2 (v3), con pipeline de senales diarias, ejecucion intradia y calibracion de umbrales por PnL. Incluye utilidades de validacion, dashboard y guias de operacion.

- Principal: [bmv_hybrid_clean_v3/README.md](bmv_hybrid_clean_v3/README.md)
- Arquitectura y despliegue: [bmv_hybrid_clean_v3/ARCHITECTURE.md](bmv_hybrid_clean_v3/ARCHITECTURE.md)
- Indice operativo: [bmv_hybrid_clean_v3/INDEX.md](bmv_hybrid_clean_v3/INDEX.md)

## Summary (EN)
Academic repository for a hybrid quantitative trading system and edge deployment components (RPi). The primary focus is BMV Hybrid V2 (v3), with a daily signal pipeline, intraday execution, and PnL-based threshold calibration. It includes validation utilities, a monitoring dashboard, and operational guides.

- Primary: [bmv_hybrid_clean_v3/README.md](bmv_hybrid_clean_v3/README.md)
- Architecture and deployment: [bmv_hybrid_clean_v3/ARCHITECTURE.md](bmv_hybrid_clean_v3/ARCHITECTURE.md)
- Operational index: [bmv_hybrid_clean_v3/INDEX.md](bmv_hybrid_clean_v3/INDEX.md)

## Repository Map
- Core system: [bmv_hybrid_clean_v3/](bmv_hybrid_clean_v3/)
- Intraday research utilities: [Intradia/](Intradia/)
- Legacy USA package: [usa_hybrid_clean_v1/usa_hybrid_clean_v1/](usa_hybrid_clean_v1/usa_hybrid_clean_v1/)
- Docs: [docs/OVERVIEW.md](docs/OVERVIEW.md), [docs/REPRODUCIBILITY.md](docs/REPRODUCIBILITY.md), [docs/STRUCTURE.md](docs/STRUCTURE.md)

## Reproducibility
See [docs/REPRODUCIBILITY.md](docs/REPRODUCIBILITY.md) for environment setup, expected data layout, and reproducible runs.

## Data, Models, and Secrets
Data, trained models, and secrets are excluded from version control. Use environment variables or local .env files (not committed) for credentials.

## Citation
If you use this work, cite it via [CITATION.cff](CITATION.cff).

## License
MIT. See [LICENSE](LICENSE).
