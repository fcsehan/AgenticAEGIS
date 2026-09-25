# Security

AEGIS is a research prototype. Its policy guarantees are conditional on a trusted
host, correct action mapping and the loaded normative rule base. Read
[the boundary and known limitations](docs/limitations.md) before integration.

The editor supports loopback-only, single-user operation. Do not expose it to a
network or reverse proxy. Use reviewed policies and keep runtime data outside the
source checkout. Do not use example domains as production compliance advice.

Report vulnerabilities privately to **frank@csehan.com**, including the affected
version, minimal reproduction, expected verdict and actual result. Avoid sending
real credentials or confidential data. Public issues are appropriate for
non-sensitive defects and documentation questions.
