# Third-party material and research foundations

The Apache-2.0 project license does not remove upstream attribution or terms.
Python and npm dependencies keep their own licenses. Dependency source trees
are not committed to this repository.

## Building Problem Solvers

The TMS, rule engine, fact indexing and pattern-matching code contains Python
adaptations of algorithms and code from *Building Problem Solvers* by Kenneth
D. Forbus and Johan de Kleer. Source docstrings identify the original routines.
The adaptations are typed Python implementations in the AEGIS architecture,
not copies of the original Lisp runtime.

The complete upstream permission and warranty notice is retained in
[licenses/BPS.txt](licenses/BPS.txt). Original per-file copyright notices are
retained in the adapted files.

Primary sources: [BPS project](https://www.qrg.northwestern.edu/BPS/readme.html),
[permission notice](https://www.qrg.northwestern.edu/BPS/legal-n.txt).

## OpenCyc knowledge-base extracts

The following files in `aegis/domains/iamission/` originate in the
[QRG OpenCyc flat-file archive](https://www.qrg.northwestern.edu/OpenCyc/opencyc_flat_files.htm),
extracted from OpenCyc 1.02 on 2007-02-14:

- `DeonticReasoning-InferenceMt.meld`
- `DeonticReasoning-LogicMt.meld`
- `DeonticReasoningWithMultiFuture-LogicMt.meld`
- `IAMissionObligationVocabMt.meld`

OpenCyc knowledge-base copyright belongs to Cycorp, Inc. QRG documents that
these extracts are redistributable. The available upstream OpenCyc legal notice
licenses the CycL knowledge base, including logically equivalent reformulations,
under Apache-2.0; it separately describes the server binary, which is not included.
That notice is preserved in [licenses/OpenCyc-LEGAL.txt](licenses/OpenCyc-LEGAL.txt),
from the [OpenCyc 4.0 source mirror](https://github.com/AndrewSmart/opencyc/blob/master/LEGAL.txt).
The original 1.02 archive does not carry a separate per-file license notice;
the 4.0 notice is identified as such rather than represented as a 1.02 artifact.

The full reference corpus, ResearchCyc, and proprietary Cyc artifacts are not
distributed here. Added provenance comments identify this packaging change;
the knowledge assertions were not rewritten during extraction.

## Web application dependencies

`aegis/editor/frontend/package-lock.json` records exact dependency versions and
license identifiers. After `npm ci`, `npm run build` collects the installed
runtime dependency license texts into `dist/THIRD_PARTY_NOTICES.txt`. This file
is included in Python packages containing the built editor.

The npm archive for `html-parse-stringify` 3.0.1 omits its MIT license text.
The build uses the retained [upstream license](https://github.com/henrikjoreteg/html-parse-stringify/blob/master/LICENSE)
in `licenses/html-parse-stringify-LICENSE.txt` (retrieved 2026-09-24).

## OpenCode integration

The integration downloads OpenCode from its upstream release; the executable
and full checkout are not redistributed in this source repository. The archived
patch contains upstream context from the MIT-licensed OpenCode project. Its
license is retained in
[integrations/opencode/patches/OPENCODE_LICENSE](integrations/opencode/patches/OPENCODE_LICENSE).
The pinned runtime npm dependency metadata is recorded in
`integrations/opencode/runtime/package-lock.json`; dependencies are downloaded
during setup and are not bundled. AEGIS integration contributions are Apache-2.0.

## Scientific attribution

- Taylor Olson, *A Formal Theory of Norms*, Northwestern University, 2025.
  [Dissertation](https://www.qrg.northwestern.edu/papers/Files/QRG_Dist_Files/QRG_2025/Olson-A_Formal_Theory_of_Norms-Final.pdf).
- Taylor Olson, Roberto Salas-Damian and Kenneth D. Forbus,
  *A Defeasible Deontic Calculus for Resolving Norm Conflicts*, 2024.
  [arXiv](https://arxiv.org/abs/2407.04869).
- Taylor Olson, Roberto Salas-Damian and Kenneth D. Forbus,
  *Reasoning and Planning with Dynamically Changing Norms*, 2026.
  [arXiv](https://arxiv.org/abs/2605.27622).

Papers, private correspondence and third-party PDF collections are not bundled.
