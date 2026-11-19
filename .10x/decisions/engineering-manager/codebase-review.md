# codebase-review (2026-11-18)
Order: stage 0 tooling -> stages 1-3 in parallel -> stage 4 verification -> report -> PR1 bugs -> PR2 simplifications -> PR3 GUI -> PR4 docs.
Slices for stage 2: A sources+pathways+input_generator+_fields; B input_reader+unparsed; C validator+validator_advanced;
D runner+runner_utils+wasm_runner+aermet/aerscreen/aersurface runners; E output_parser+aermod_outputs+postfile;
F design_values+naaqs+psd+regulatory+regulatory_parity+chemistry_presets; G aermet+aermap+terrain+terrain_utils+geospatial+visualization+advanced_viz+kmz_export;
H ensemble+api+cli+aerscreen+aersurface+bpip+prime+receptors+met_*+source_importers+hourly_emissions+footprints.
