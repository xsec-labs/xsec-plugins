# Third-party notices

The plugin source is licensed under GPL-3.0-only; see `LICENSE`.

- **jwt_tool 2.3.0**: source files in `jwt_tool/`, from the upstream [v2.3.0 release](https://github.com/ticarpi/jwt_tool/tree/v2.3.0), GPL-3.0. The full upstream license is `third_party/LICENSE.jwt_tool`.
- **RockYou**: `wordlists/rockyou.txt.tar.gz`, from SecLists `Passwords/Leaked-Databases/rockyou.txt.tar.gz`, MIT. SHA-256: `47c070a029bcdb4cbd0e02c69fed136ef46dce4048ddbadf177daa5e885b8172`. License: `third_party/LICENSE.seclists`.
- **Runtime dependencies**: Requests 2.34.2 (Apache-2.0), PyCryptodomex 3.23.0 (BSD-2-Clause and public-domain components), termcolor 3.3.0 (MIT), ratelimit 2.2.1 (MIT), urllib3 2.6.3 (MIT), idna 3.13 (BSD-3-Clause), certifi 2026.4.22 (MPL-2.0), charset-normalizer 3.4.7 (MIT).
- **Build dependencies**: PyInstaller 6.22.3 (GPL-2.0-or-later with its bootloader exception; bundled runtime helper modules are Apache-2.0), PyInstaller-hooks-contrib 2026.7, altgraph 0.17.5, and packaging 26.2. Their license texts are included in `third_party/`.

The exact direct and transitive versions are pinned in `requirements-runtime.lock` and `requirements-build.lock`. The CycloneDX SBOM is `third_party/sbom.cdx.json`. The packaged executable is built independently on a matching OS/architecture runner; no cross-compilation is claimed.
