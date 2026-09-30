# Third-party notices and provenance

The original code in this repository is independently implemented. It is not a fork or wholesale copy of Malps-del/lspp-mcp-server. That project's architecture and static review findings informed the job isolation, artifact verification and source/capability separation used here.

## Redistributed command catalog

`src/ls_prepost_mcp/data/commands.tsv` is copied without intentional modification from [Hydrowelder/lsdyna-ls-prepost-cfile-support](https://github.com/Hydrowelder/lsdyna-ls-prepost-cfile-support/blob/main/valid_commands.tsv), retrieved 2026-09-30. Attribution: Hydrowelder and contributors. The upstream Apache License 2.0 is preserved in `third_party/cfile-support/LICENSE`.

This catalog is reference material. Upstream explicitly reports no command validation. Inclusion does not certify syntax, version support, effects, or compatibility with any installed LS-PrePost build.

## Referenced, not redistributed

- Ansys LS-PrePost User's Guide, tutorials and SCL/Python API documentation: source links and authored semantic/acceptance summaries only.
- Malps-del/lspp-mcp-server, Ansys-LSPP-AgentKit, K-agent and the other indexed repositories: attribution and findings, not copied server code.
- Local SCL/Python examples and research scripts: extracted capability descriptions, API names and failure cases; original files and models remain local.
- Projects with absent or custom licensing, including UMAT_2scale_LSDYNA, KooD3plotReader and several script collections, are reference-only until their reuse terms are resolved.

Optional `lasso-python` is installed as a dependency under its own BSD-3-Clause license. PyDYNA is a planned optional backend, not yet part of the runtime implementation. Neither dependency license grants rights to vendor software.

