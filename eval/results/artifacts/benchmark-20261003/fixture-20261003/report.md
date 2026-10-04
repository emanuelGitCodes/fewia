# Evaluation report

## Coverage

| Coverage | Count |
| --- | --- |
| Primary slots | 90 |
| Baseline slots | 48 |
| Total slots | 138 |
| Scored slots | 129 |
| Unassessed slots | 9 |
| Execution\-failed slots | 0 |

Scored includes passed and failed quality assessments in complete evaluation mode.

## Metadata

| Field | Value |
| --- | --- |
| Mode | complete\_evaluation |
| Revision | 4b877d470258561cedd3375e38efc02362ce5f22 |
| UTC start | 2026\-10\-03T22\:43\:42\.860988\+00\:00 |
| UTC end | 2026\-10\-03T22\:43\:43\.975452\+00\:00 |
| Manifest version | evaluation\-manifest\-v1 |
| model id | us\.amazon\.nova\-2\-lite\-v1\:0 |
| region | us\-east\-1 |
| catalog version | sample\-prices\-v2 |
| max\_tokens | 4096 |
| temperature | 0 |
| reasoning\_effort | low |
| Condition | tool\_enabled |
| Condition | no\_tool |
| Condition | deterministic |
| manifest\_hash | 34888d692bee873021cbfc2478b479ed62badbc045f3c83618ad511eb720778d |
| corpus\_hash | bf72e0d4021c2dd37f69311894e1893ef6272e82e207933bafc30607473dbbe4 |
| catalog\_hash | 89361b6a53b35016d379a2446265c530348ad24b915564bca982fc00f6e3eb2f |
| system\_prompt\_hash | e91c08b52032242aeb1f0f16d8c91a3d0840a64a140252013ad2b1903fdbc891 |
| baseline\_system\_prompt\_hash | 102fb3fa12470fa1992b906f3d92d960c81faf66beb3dfe6fd0ccbb90272d374 |
| model\_config\_hash | 9f9e812cd127182909e4e22dd0cb3825d7b47e156c5d835c1df8f7fb787c9987 |

Quality is scoped by condition and evidence. Deterministic fixture, reference, and fake evidence does not establish real-model quality. Unknown values remain unknown. Empty findings do not establish that targets are met.

## Quality

### controlled\_fixture / deterministic\_fake\_provider

| Task passed\/applicable | Task passed\/assessed | Failed | Unassessed | Not applicable | Quality scope |
| --- | --- | --- | --- | --- | --- |
| 12\/12 | 12\/12 | 0 | 0 | 0 | fixture\_guard |

| Tool metric | Numerator\/denominator | Unassessed |
| --- | --- | --- |
| Valid calls | 0\/0 \(unassessed\) | 0 |
| Expected tool selection | 0\/0 \(unassessed\) | 0 |
| Expected arguments | 0\/0 \(unassessed\) | 0 |
| Unnecessary calls \(lower is better\) | 0\/0 \(unassessed\) | 0 |

| Public claims supported\/assessed | Public claims supported\/\(assessed\+unknown\) | Unknown | Unsupported | Supported refusals |
| --- | --- | --- | --- | --- |
| 0\/0 \(unassessed\) | 0\/0 \(unassessed\) | 0 | 0 | 0 |

| Assessment | Passed\/assessed | Unassessed |
| --- | --- | --- |
| Plan | 0\/0 \(unassessed\) | 0 |
| Outcome | 0\/0 \(unassessed\) | 0 |
| Fixture | 12\/12 | 0 |
| Clarification correctness | 0\/0 \(unassessed\) | 0 |

### controlled\_fixture / local\_postgresql

| Task passed\/applicable | Task passed\/assessed | Failed | Unassessed | Not applicable | Quality scope |
| --- | --- | --- | --- | --- | --- |
| 3\/3 | 3\/3 | 0 | 0 | 0 | fixture\_guard |

| Tool metric | Numerator\/denominator | Unassessed |
| --- | --- | --- |
| Valid calls | 0\/0 \(unassessed\) | 0 |
| Expected tool selection | 0\/0 \(unassessed\) | 0 |
| Expected arguments | 0\/0 \(unassessed\) | 0 |
| Unnecessary calls \(lower is better\) | 0\/0 \(unassessed\) | 0 |

| Public claims supported\/assessed | Public claims supported\/\(assessed\+unknown\) | Unknown | Unsupported | Supported refusals |
| --- | --- | --- | --- | --- |
| 0\/0 \(unassessed\) | 0\/0 \(unassessed\) | 0 | 0 | 0 |

| Assessment | Passed\/assessed | Unassessed |
| --- | --- | --- |
| Plan | 0\/0 \(unassessed\) | 0 |
| Outcome | 0\/0 \(unassessed\) | 0 |
| Fixture | 3\/3 | 0 |
| Clarification correctness | 0\/0 \(unassessed\) | 0 |

### deterministic / deterministic\_fake\_provider

| Task passed\/applicable | Task passed\/assessed | Failed | Unassessed | Not applicable | Quality scope |
| --- | --- | --- | --- | --- | --- |
| 15\/15 | 15\/15 | 0 | 0 | 0 | structured\_reference |

| Tool metric | Numerator\/denominator | Unassessed |
| --- | --- | --- |
| Valid calls | 0\/0 \(unassessed\) | 0 |
| Expected tool selection | 0\/0 \(unassessed\) | 0 |
| Expected arguments | 0\/0 \(unassessed\) | 0 |
| Unnecessary calls \(lower is better\) | 0\/0 \(unassessed\) | 0 |

| Public claims supported\/assessed | Public claims supported\/\(assessed\+unknown\) | Unknown | Unsupported | Supported refusals |
| --- | --- | --- | --- | --- |
| 0\/0 \(unassessed\) | 0\/0 \(unassessed\) | 0 | 0 | 0 |

| Assessment | Passed\/assessed | Unassessed |
| --- | --- | --- |
| Plan | 15\/15 | 0 |
| Outcome | 0\/0 \(unassessed\) | 0 |
| Fixture | 0\/0 \(unassessed\) | 0 |
| Clarification correctness | 0\/0 \(unassessed\) | 0 |

### deterministic\_fixture / deterministic\_fake\_provider

| Task passed\/applicable | Task passed\/assessed | Failed | Unassessed | Not applicable | Quality scope |
| --- | --- | --- | --- | --- | --- |
| 42\/42 | 42\/42 | 0 | 0 | 0 | fixture\_guard |

| Tool metric | Numerator\/denominator | Unassessed |
| --- | --- | --- |
| Valid calls | 0\/0 \(unassessed\) | 0 |
| Expected tool selection | 0\/0 \(unassessed\) | 0 |
| Expected arguments | 0\/0 \(unassessed\) | 0 |
| Unnecessary calls \(lower is better\) | 0\/0 \(unassessed\) | 0 |

| Public claims supported\/assessed | Public claims supported\/\(assessed\+unknown\) | Unknown | Unsupported | Supported refusals |
| --- | --- | --- | --- | --- |
| 0\/0 \(unassessed\) | 0\/0 \(unassessed\) | 0 | 0 | 0 |

| Assessment | Passed\/assessed | Unassessed |
| --- | --- | --- |
| Plan | 0\/0 \(unassessed\) | 0 |
| Outcome | 0\/0 \(unassessed\) | 0 |
| Fixture | 42\/42 | 0 |
| Clarification correctness | 0\/0 \(unassessed\) | 0 |

### no\_tool / deterministic\_fake\_provider

| Task passed\/applicable | Task passed\/assessed | Failed | Unassessed | Not applicable | Quality scope |
| --- | --- | --- | --- | --- | --- |
| 0\/33 | 0\/24 | 24 | 9 | 0 | language\_task |

| Tool metric | Numerator\/denominator | Unassessed |
| --- | --- | --- |
| Valid calls | 0\/0 \(unassessed\) | 0 |
| Expected tool selection | 0\/0 \(unassessed\) | 0 |
| Expected arguments | 0\/0 \(unassessed\) | 0 |
| Unnecessary calls \(lower is better\) | 0\/0 \(unassessed\) | 0 |

| Public claims supported\/assessed | Public claims supported\/\(assessed\+unknown\) | Unknown | Unsupported | Supported refusals |
| --- | --- | --- | --- | --- |
| 0\/0 \(unassessed\) | 0\/48 | 48 | 0 | 0 |

| Assessment | Passed\/assessed | Unassessed |
| --- | --- | --- |
| Plan | 0\/15 | 0 |
| Outcome | 0\/0 \(unassessed\) | 33 |
| Fixture | 0\/0 \(unassessed\) | 0 |
| Clarification correctness | 0\/0 \(unassessed\) | 9 |

### tool\_enabled / deterministic\_fake\_provider

| Task passed\/applicable | Task passed\/assessed | Failed | Unassessed | Not applicable | Quality scope |
| --- | --- | --- | --- | --- | --- |
| 3\/33 | 3\/33 | 30 | 0 | 0 | language\_task |

| Tool metric | Numerator\/denominator | Unassessed |
| --- | --- | --- |
| Valid calls | 0\/0 \(unassessed\) | 0 |
| Expected tool selection | 0\/24 | 0 |
| Expected arguments | 0\/24 | 0 |
| Unnecessary calls \(lower is better\) | 0\/0 \(unassessed\) | 0 |

| Public claims supported\/assessed | Public claims supported\/\(assessed\+unknown\) | Unknown | Unsupported | Supported refusals |
| --- | --- | --- | --- | --- |
| 48\/48 | 48\/48 | 0 | 0 | 0 |

| Assessment | Passed\/assessed | Unassessed |
| --- | --- | --- |
| Plan | 0\/15 | 0 |
| Outcome | 6\/18 | 15 |
| Fixture | 0\/0 \(unassessed\) | 0 |
| Clarification correctness | 6\/9 | 0 |

## Quality failures

| Case | Repeat | Condition | Evidence | Assessment | Failed check |
| --- | --- | --- | --- | --- | --- |
| F01 | 1 | no\_tool | deterministic\_fake\_provider | plan | final\_plan\_present |
| F01 | 1 | no\_tool | deterministic\_fake\_provider | plan | request\_meals |
| F01 | 1 | no\_tool | deterministic\_fake\_provider | plan | request\_diet |
| F01 | 1 | no\_tool | deterministic\_fake\_provider | plan | request\_budget\_period |
| F01 | 1 | no\_tool | deterministic\_fake\_provider | plan | request\_plan\_cap\_cents |
| F01 | 1 | no\_tool | deterministic\_fake\_provider | plan | request\_pantry\_ingredients |
| F01 | 1 | no\_tool | deterministic\_fake\_provider | plan | request\_ingredient\_exclusions |
| F01 | 1 | no\_tool | deterministic\_fake\_provider | plan | expected\_accepted |
| F01 | 1 | no\_tool | deterministic\_fake\_provider | plan | expected\_total\_cents |
| F01 | 1 | no\_tool | deterministic\_fake\_provider | plan | expected\_notice |
| F01 | 1 | no\_tool | deterministic\_fake\_provider | plan | expected\_catalog\_version |
| F01 | 1 | no\_tool | deterministic\_fake\_provider | plan | expected\_budget\_available\_cents |
| F01 | 1 | no\_tool | deterministic\_fake\_provider | plan | budget\_arithmetic |
| F01 | 1 | no\_tool | deterministic\_fake\_provider | plan | budget\_pending |
| F01 | 1 | no\_tool | deterministic\_fake\_provider | plan | budget\_stale |
| F01 | 1 | no\_tool | deterministic\_fake\_provider | plan | golden\_lines |
| F01 | 1 | no\_tool | deterministic\_fake\_provider | plan | integrity\_ingredient\_coverage |
| F01 | 1 | no\_tool | deterministic\_fake\_provider | plan | integrity\_quantities |
| F01 | 1 | no\_tool | deterministic\_fake\_provider | plan | integrity\_package\_rounding |
| F01 | 1 | no\_tool | deterministic\_fake\_provider | plan | integrity\_sample\_costs |
| F01 | 1 | no\_tool | deterministic\_fake\_provider | plan | integrity\_diet |
| F01 | 1 | no\_tool | deterministic\_fake\_provider | plan | integrity\_exclusions |
| F01 | 1 | no\_tool | deterministic\_fake\_provider | plan | integrity\_total\_cents |
| F01 | 1 | no\_tool | deterministic\_fake\_provider | plan | integrity\_acceptance |
| F01 | 1 | no\_tool | deterministic\_fake\_provider | plan | integrity\_budget\_cap |
| F01 | 1 | no\_tool | deterministic\_fake\_provider | plan | integrity\_notice |
| F01 | 1 | no\_tool | deterministic\_fake\_provider | plan | integrity\_catalog\_version |
| F01 | 1 | no\_tool | deterministic\_fake\_provider | plan | integrity\_schema |
| F01 | 2 | no\_tool | deterministic\_fake\_provider | plan | final\_plan\_present |
| F01 | 2 | no\_tool | deterministic\_fake\_provider | plan | request\_meals |
| F01 | 2 | no\_tool | deterministic\_fake\_provider | plan | request\_diet |
| F01 | 2 | no\_tool | deterministic\_fake\_provider | plan | request\_budget\_period |
| F01 | 2 | no\_tool | deterministic\_fake\_provider | plan | request\_plan\_cap\_cents |
| F01 | 2 | no\_tool | deterministic\_fake\_provider | plan | request\_pantry\_ingredients |
| F01 | 2 | no\_tool | deterministic\_fake\_provider | plan | request\_ingredient\_exclusions |
| F01 | 2 | no\_tool | deterministic\_fake\_provider | plan | expected\_accepted |
| F01 | 2 | no\_tool | deterministic\_fake\_provider | plan | expected\_total\_cents |
| F01 | 2 | no\_tool | deterministic\_fake\_provider | plan | expected\_notice |
| F01 | 2 | no\_tool | deterministic\_fake\_provider | plan | expected\_catalog\_version |
| F01 | 2 | no\_tool | deterministic\_fake\_provider | plan | expected\_budget\_available\_cents |
| F01 | 2 | no\_tool | deterministic\_fake\_provider | plan | budget\_arithmetic |
| F01 | 2 | no\_tool | deterministic\_fake\_provider | plan | budget\_pending |
| F01 | 2 | no\_tool | deterministic\_fake\_provider | plan | budget\_stale |
| F01 | 2 | no\_tool | deterministic\_fake\_provider | plan | golden\_lines |
| F01 | 2 | no\_tool | deterministic\_fake\_provider | plan | integrity\_ingredient\_coverage |
| F01 | 2 | no\_tool | deterministic\_fake\_provider | plan | integrity\_quantities |
| F01 | 2 | no\_tool | deterministic\_fake\_provider | plan | integrity\_package\_rounding |
| F01 | 2 | no\_tool | deterministic\_fake\_provider | plan | integrity\_sample\_costs |
| F01 | 2 | no\_tool | deterministic\_fake\_provider | plan | integrity\_diet |
| F01 | 2 | no\_tool | deterministic\_fake\_provider | plan | integrity\_exclusions |
| F01 | 2 | no\_tool | deterministic\_fake\_provider | plan | integrity\_total\_cents |
| F01 | 2 | no\_tool | deterministic\_fake\_provider | plan | integrity\_acceptance |
| F01 | 2 | no\_tool | deterministic\_fake\_provider | plan | integrity\_budget\_cap |
| F01 | 2 | no\_tool | deterministic\_fake\_provider | plan | integrity\_notice |
| F01 | 2 | no\_tool | deterministic\_fake\_provider | plan | integrity\_catalog\_version |
| F01 | 2 | no\_tool | deterministic\_fake\_provider | plan | integrity\_schema |
| F01 | 3 | no\_tool | deterministic\_fake\_provider | plan | final\_plan\_present |
| F01 | 3 | no\_tool | deterministic\_fake\_provider | plan | request\_meals |
| F01 | 3 | no\_tool | deterministic\_fake\_provider | plan | request\_diet |
| F01 | 3 | no\_tool | deterministic\_fake\_provider | plan | request\_budget\_period |
| F01 | 3 | no\_tool | deterministic\_fake\_provider | plan | request\_plan\_cap\_cents |
| F01 | 3 | no\_tool | deterministic\_fake\_provider | plan | request\_pantry\_ingredients |
| F01 | 3 | no\_tool | deterministic\_fake\_provider | plan | request\_ingredient\_exclusions |
| F01 | 3 | no\_tool | deterministic\_fake\_provider | plan | expected\_accepted |
| F01 | 3 | no\_tool | deterministic\_fake\_provider | plan | expected\_total\_cents |
| F01 | 3 | no\_tool | deterministic\_fake\_provider | plan | expected\_notice |
| F01 | 3 | no\_tool | deterministic\_fake\_provider | plan | expected\_catalog\_version |
| F01 | 3 | no\_tool | deterministic\_fake\_provider | plan | expected\_budget\_available\_cents |
| F01 | 3 | no\_tool | deterministic\_fake\_provider | plan | budget\_arithmetic |
| F01 | 3 | no\_tool | deterministic\_fake\_provider | plan | budget\_pending |
| F01 | 3 | no\_tool | deterministic\_fake\_provider | plan | budget\_stale |
| F01 | 3 | no\_tool | deterministic\_fake\_provider | plan | golden\_lines |
| F01 | 3 | no\_tool | deterministic\_fake\_provider | plan | integrity\_ingredient\_coverage |
| F01 | 3 | no\_tool | deterministic\_fake\_provider | plan | integrity\_quantities |
| F01 | 3 | no\_tool | deterministic\_fake\_provider | plan | integrity\_package\_rounding |
| F01 | 3 | no\_tool | deterministic\_fake\_provider | plan | integrity\_sample\_costs |
| F01 | 3 | no\_tool | deterministic\_fake\_provider | plan | integrity\_diet |
| F01 | 3 | no\_tool | deterministic\_fake\_provider | plan | integrity\_exclusions |
| F01 | 3 | no\_tool | deterministic\_fake\_provider | plan | integrity\_total\_cents |
| F01 | 3 | no\_tool | deterministic\_fake\_provider | plan | integrity\_acceptance |
| F01 | 3 | no\_tool | deterministic\_fake\_provider | plan | integrity\_budget\_cap |
| F01 | 3 | no\_tool | deterministic\_fake\_provider | plan | integrity\_notice |
| F01 | 3 | no\_tool | deterministic\_fake\_provider | plan | integrity\_catalog\_version |
| F01 | 3 | no\_tool | deterministic\_fake\_provider | plan | integrity\_schema |
| F02 | 1 | no\_tool | deterministic\_fake\_provider | plan | final\_plan\_present |
| F02 | 1 | no\_tool | deterministic\_fake\_provider | plan | request\_meals |
| F02 | 1 | no\_tool | deterministic\_fake\_provider | plan | request\_diet |
| F02 | 1 | no\_tool | deterministic\_fake\_provider | plan | request\_budget\_period |
| F02 | 1 | no\_tool | deterministic\_fake\_provider | plan | request\_plan\_cap\_cents |
| F02 | 1 | no\_tool | deterministic\_fake\_provider | plan | request\_pantry\_ingredients |
| F02 | 1 | no\_tool | deterministic\_fake\_provider | plan | request\_ingredient\_exclusions |
| F02 | 1 | no\_tool | deterministic\_fake\_provider | plan | expected\_accepted |
| F02 | 1 | no\_tool | deterministic\_fake\_provider | plan | expected\_total\_cents |
| F02 | 1 | no\_tool | deterministic\_fake\_provider | plan | expected\_notice |
| F02 | 1 | no\_tool | deterministic\_fake\_provider | plan | expected\_catalog\_version |
| F02 | 1 | no\_tool | deterministic\_fake\_provider | plan | expected\_budget\_available\_cents |
| F02 | 1 | no\_tool | deterministic\_fake\_provider | plan | budget\_arithmetic |
| F02 | 1 | no\_tool | deterministic\_fake\_provider | plan | budget\_pending |
| F02 | 1 | no\_tool | deterministic\_fake\_provider | plan | budget\_stale |
| F02 | 1 | no\_tool | deterministic\_fake\_provider | plan | golden\_lines |
| F02 | 1 | no\_tool | deterministic\_fake\_provider | plan | integrity\_ingredient\_coverage |
| F02 | 1 | no\_tool | deterministic\_fake\_provider | plan | integrity\_quantities |
| F02 | 1 | no\_tool | deterministic\_fake\_provider | plan | integrity\_package\_rounding |
| F02 | 1 | no\_tool | deterministic\_fake\_provider | plan | integrity\_sample\_costs |
| F02 | 1 | no\_tool | deterministic\_fake\_provider | plan | integrity\_diet |
| F02 | 1 | no\_tool | deterministic\_fake\_provider | plan | integrity\_exclusions |
| F02 | 1 | no\_tool | deterministic\_fake\_provider | plan | integrity\_total\_cents |
| F02 | 1 | no\_tool | deterministic\_fake\_provider | plan | integrity\_acceptance |
| F02 | 1 | no\_tool | deterministic\_fake\_provider | plan | integrity\_budget\_cap |
| F02 | 1 | no\_tool | deterministic\_fake\_provider | plan | integrity\_notice |
| F02 | 1 | no\_tool | deterministic\_fake\_provider | plan | integrity\_catalog\_version |
| F02 | 1 | no\_tool | deterministic\_fake\_provider | plan | integrity\_schema |
| F02 | 2 | no\_tool | deterministic\_fake\_provider | plan | final\_plan\_present |
| F02 | 2 | no\_tool | deterministic\_fake\_provider | plan | request\_meals |
| F02 | 2 | no\_tool | deterministic\_fake\_provider | plan | request\_diet |
| F02 | 2 | no\_tool | deterministic\_fake\_provider | plan | request\_budget\_period |
| F02 | 2 | no\_tool | deterministic\_fake\_provider | plan | request\_plan\_cap\_cents |
| F02 | 2 | no\_tool | deterministic\_fake\_provider | plan | request\_pantry\_ingredients |
| F02 | 2 | no\_tool | deterministic\_fake\_provider | plan | request\_ingredient\_exclusions |
| F02 | 2 | no\_tool | deterministic\_fake\_provider | plan | expected\_accepted |
| F02 | 2 | no\_tool | deterministic\_fake\_provider | plan | expected\_total\_cents |
| F02 | 2 | no\_tool | deterministic\_fake\_provider | plan | expected\_notice |
| F02 | 2 | no\_tool | deterministic\_fake\_provider | plan | expected\_catalog\_version |
| F02 | 2 | no\_tool | deterministic\_fake\_provider | plan | expected\_budget\_available\_cents |
| F02 | 2 | no\_tool | deterministic\_fake\_provider | plan | budget\_arithmetic |
| F02 | 2 | no\_tool | deterministic\_fake\_provider | plan | budget\_pending |
| F02 | 2 | no\_tool | deterministic\_fake\_provider | plan | budget\_stale |
| F02 | 2 | no\_tool | deterministic\_fake\_provider | plan | golden\_lines |
| F02 | 2 | no\_tool | deterministic\_fake\_provider | plan | integrity\_ingredient\_coverage |
| F02 | 2 | no\_tool | deterministic\_fake\_provider | plan | integrity\_quantities |
| F02 | 2 | no\_tool | deterministic\_fake\_provider | plan | integrity\_package\_rounding |
| F02 | 2 | no\_tool | deterministic\_fake\_provider | plan | integrity\_sample\_costs |
| F02 | 2 | no\_tool | deterministic\_fake\_provider | plan | integrity\_diet |
| F02 | 2 | no\_tool | deterministic\_fake\_provider | plan | integrity\_exclusions |
| F02 | 2 | no\_tool | deterministic\_fake\_provider | plan | integrity\_total\_cents |
| F02 | 2 | no\_tool | deterministic\_fake\_provider | plan | integrity\_acceptance |
| F02 | 2 | no\_tool | deterministic\_fake\_provider | plan | integrity\_budget\_cap |
| F02 | 2 | no\_tool | deterministic\_fake\_provider | plan | integrity\_notice |
| F02 | 2 | no\_tool | deterministic\_fake\_provider | plan | integrity\_catalog\_version |
| F02 | 2 | no\_tool | deterministic\_fake\_provider | plan | integrity\_schema |
| F02 | 3 | no\_tool | deterministic\_fake\_provider | plan | final\_plan\_present |
| F02 | 3 | no\_tool | deterministic\_fake\_provider | plan | request\_meals |
| F02 | 3 | no\_tool | deterministic\_fake\_provider | plan | request\_diet |
| F02 | 3 | no\_tool | deterministic\_fake\_provider | plan | request\_budget\_period |
| F02 | 3 | no\_tool | deterministic\_fake\_provider | plan | request\_plan\_cap\_cents |
| F02 | 3 | no\_tool | deterministic\_fake\_provider | plan | request\_pantry\_ingredients |
| F02 | 3 | no\_tool | deterministic\_fake\_provider | plan | request\_ingredient\_exclusions |
| F02 | 3 | no\_tool | deterministic\_fake\_provider | plan | expected\_accepted |
| F02 | 3 | no\_tool | deterministic\_fake\_provider | plan | expected\_total\_cents |
| F02 | 3 | no\_tool | deterministic\_fake\_provider | plan | expected\_notice |
| F02 | 3 | no\_tool | deterministic\_fake\_provider | plan | expected\_catalog\_version |
| F02 | 3 | no\_tool | deterministic\_fake\_provider | plan | expected\_budget\_available\_cents |
| F02 | 3 | no\_tool | deterministic\_fake\_provider | plan | budget\_arithmetic |
| F02 | 3 | no\_tool | deterministic\_fake\_provider | plan | budget\_pending |
| F02 | 3 | no\_tool | deterministic\_fake\_provider | plan | budget\_stale |
| F02 | 3 | no\_tool | deterministic\_fake\_provider | plan | golden\_lines |
| F02 | 3 | no\_tool | deterministic\_fake\_provider | plan | integrity\_ingredient\_coverage |
| F02 | 3 | no\_tool | deterministic\_fake\_provider | plan | integrity\_quantities |
| F02 | 3 | no\_tool | deterministic\_fake\_provider | plan | integrity\_package\_rounding |
| F02 | 3 | no\_tool | deterministic\_fake\_provider | plan | integrity\_sample\_costs |
| F02 | 3 | no\_tool | deterministic\_fake\_provider | plan | integrity\_diet |
| F02 | 3 | no\_tool | deterministic\_fake\_provider | plan | integrity\_exclusions |
| F02 | 3 | no\_tool | deterministic\_fake\_provider | plan | integrity\_total\_cents |
| F02 | 3 | no\_tool | deterministic\_fake\_provider | plan | integrity\_acceptance |
| F02 | 3 | no\_tool | deterministic\_fake\_provider | plan | integrity\_budget\_cap |
| F02 | 3 | no\_tool | deterministic\_fake\_provider | plan | integrity\_notice |
| F02 | 3 | no\_tool | deterministic\_fake\_provider | plan | integrity\_catalog\_version |
| F02 | 3 | no\_tool | deterministic\_fake\_provider | plan | integrity\_schema |
| F05 | 1 | no\_tool | deterministic\_fake\_provider | plan | final\_plan\_present |
| F05 | 1 | no\_tool | deterministic\_fake\_provider | plan | request\_meals |
| F05 | 1 | no\_tool | deterministic\_fake\_provider | plan | request\_diet |
| F05 | 1 | no\_tool | deterministic\_fake\_provider | plan | request\_budget\_period |
| F05 | 1 | no\_tool | deterministic\_fake\_provider | plan | request\_plan\_cap\_cents |
| F05 | 1 | no\_tool | deterministic\_fake\_provider | plan | request\_pantry\_ingredients |
| F05 | 1 | no\_tool | deterministic\_fake\_provider | plan | request\_ingredient\_exclusions |
| F05 | 1 | no\_tool | deterministic\_fake\_provider | plan | expected\_accepted |
| F05 | 1 | no\_tool | deterministic\_fake\_provider | plan | expected\_total\_cents |
| F05 | 1 | no\_tool | deterministic\_fake\_provider | plan | expected\_notice |
| F05 | 1 | no\_tool | deterministic\_fake\_provider | plan | expected\_catalog\_version |
| F05 | 1 | no\_tool | deterministic\_fake\_provider | plan | budget\_arithmetic |
| F05 | 1 | no\_tool | deterministic\_fake\_provider | plan | budget\_pending |
| F05 | 1 | no\_tool | deterministic\_fake\_provider | plan | budget\_stale |
| F05 | 1 | no\_tool | deterministic\_fake\_provider | plan | golden\_lines |
| F05 | 1 | no\_tool | deterministic\_fake\_provider | plan | integrity\_ingredient\_coverage |
| F05 | 1 | no\_tool | deterministic\_fake\_provider | plan | integrity\_quantities |
| F05 | 1 | no\_tool | deterministic\_fake\_provider | plan | integrity\_package\_rounding |
| F05 | 1 | no\_tool | deterministic\_fake\_provider | plan | integrity\_sample\_costs |
| F05 | 1 | no\_tool | deterministic\_fake\_provider | plan | integrity\_diet |
| F05 | 1 | no\_tool | deterministic\_fake\_provider | plan | integrity\_exclusions |
| F05 | 1 | no\_tool | deterministic\_fake\_provider | plan | integrity\_total\_cents |
| F05 | 1 | no\_tool | deterministic\_fake\_provider | plan | integrity\_acceptance |
| F05 | 1 | no\_tool | deterministic\_fake\_provider | plan | integrity\_budget\_cap |
| F05 | 1 | no\_tool | deterministic\_fake\_provider | plan | integrity\_notice |
| F05 | 1 | no\_tool | deterministic\_fake\_provider | plan | integrity\_catalog\_version |
| F05 | 1 | no\_tool | deterministic\_fake\_provider | plan | integrity\_schema |
| F05 | 2 | no\_tool | deterministic\_fake\_provider | plan | final\_plan\_present |
| F05 | 2 | no\_tool | deterministic\_fake\_provider | plan | request\_meals |
| F05 | 2 | no\_tool | deterministic\_fake\_provider | plan | request\_diet |
| F05 | 2 | no\_tool | deterministic\_fake\_provider | plan | request\_budget\_period |
| F05 | 2 | no\_tool | deterministic\_fake\_provider | plan | request\_plan\_cap\_cents |
| F05 | 2 | no\_tool | deterministic\_fake\_provider | plan | request\_pantry\_ingredients |
| F05 | 2 | no\_tool | deterministic\_fake\_provider | plan | request\_ingredient\_exclusions |
| F05 | 2 | no\_tool | deterministic\_fake\_provider | plan | expected\_accepted |
| F05 | 2 | no\_tool | deterministic\_fake\_provider | plan | expected\_total\_cents |
| F05 | 2 | no\_tool | deterministic\_fake\_provider | plan | expected\_notice |
| F05 | 2 | no\_tool | deterministic\_fake\_provider | plan | expected\_catalog\_version |
| F05 | 2 | no\_tool | deterministic\_fake\_provider | plan | budget\_arithmetic |
| F05 | 2 | no\_tool | deterministic\_fake\_provider | plan | budget\_pending |
| F05 | 2 | no\_tool | deterministic\_fake\_provider | plan | budget\_stale |
| F05 | 2 | no\_tool | deterministic\_fake\_provider | plan | golden\_lines |
| F05 | 2 | no\_tool | deterministic\_fake\_provider | plan | integrity\_ingredient\_coverage |
| F05 | 2 | no\_tool | deterministic\_fake\_provider | plan | integrity\_quantities |
| F05 | 2 | no\_tool | deterministic\_fake\_provider | plan | integrity\_package\_rounding |
| F05 | 2 | no\_tool | deterministic\_fake\_provider | plan | integrity\_sample\_costs |
| F05 | 2 | no\_tool | deterministic\_fake\_provider | plan | integrity\_diet |
| F05 | 2 | no\_tool | deterministic\_fake\_provider | plan | integrity\_exclusions |
| F05 | 2 | no\_tool | deterministic\_fake\_provider | plan | integrity\_total\_cents |
| F05 | 2 | no\_tool | deterministic\_fake\_provider | plan | integrity\_acceptance |
| F05 | 2 | no\_tool | deterministic\_fake\_provider | plan | integrity\_budget\_cap |
| F05 | 2 | no\_tool | deterministic\_fake\_provider | plan | integrity\_notice |
| F05 | 2 | no\_tool | deterministic\_fake\_provider | plan | integrity\_catalog\_version |
| F05 | 2 | no\_tool | deterministic\_fake\_provider | plan | integrity\_schema |
| F05 | 3 | no\_tool | deterministic\_fake\_provider | plan | final\_plan\_present |
| F05 | 3 | no\_tool | deterministic\_fake\_provider | plan | request\_meals |
| F05 | 3 | no\_tool | deterministic\_fake\_provider | plan | request\_diet |
| F05 | 3 | no\_tool | deterministic\_fake\_provider | plan | request\_budget\_period |
| F05 | 3 | no\_tool | deterministic\_fake\_provider | plan | request\_plan\_cap\_cents |
| F05 | 3 | no\_tool | deterministic\_fake\_provider | plan | request\_pantry\_ingredients |
| F05 | 3 | no\_tool | deterministic\_fake\_provider | plan | request\_ingredient\_exclusions |
| F05 | 3 | no\_tool | deterministic\_fake\_provider | plan | expected\_accepted |
| F05 | 3 | no\_tool | deterministic\_fake\_provider | plan | expected\_total\_cents |
| F05 | 3 | no\_tool | deterministic\_fake\_provider | plan | expected\_notice |
| F05 | 3 | no\_tool | deterministic\_fake\_provider | plan | expected\_catalog\_version |
| F05 | 3 | no\_tool | deterministic\_fake\_provider | plan | budget\_arithmetic |
| F05 | 3 | no\_tool | deterministic\_fake\_provider | plan | budget\_pending |
| F05 | 3 | no\_tool | deterministic\_fake\_provider | plan | budget\_stale |
| F05 | 3 | no\_tool | deterministic\_fake\_provider | plan | golden\_lines |
| F05 | 3 | no\_tool | deterministic\_fake\_provider | plan | integrity\_ingredient\_coverage |
| F05 | 3 | no\_tool | deterministic\_fake\_provider | plan | integrity\_quantities |
| F05 | 3 | no\_tool | deterministic\_fake\_provider | plan | integrity\_package\_rounding |
| F05 | 3 | no\_tool | deterministic\_fake\_provider | plan | integrity\_sample\_costs |
| F05 | 3 | no\_tool | deterministic\_fake\_provider | plan | integrity\_diet |
| F05 | 3 | no\_tool | deterministic\_fake\_provider | plan | integrity\_exclusions |
| F05 | 3 | no\_tool | deterministic\_fake\_provider | plan | integrity\_total\_cents |
| F05 | 3 | no\_tool | deterministic\_fake\_provider | plan | integrity\_acceptance |
| F05 | 3 | no\_tool | deterministic\_fake\_provider | plan | integrity\_budget\_cap |
| F05 | 3 | no\_tool | deterministic\_fake\_provider | plan | integrity\_notice |
| F05 | 3 | no\_tool | deterministic\_fake\_provider | plan | integrity\_catalog\_version |
| F05 | 3 | no\_tool | deterministic\_fake\_provider | plan | integrity\_schema |
| X04 | 1 | no\_tool | deterministic\_fake\_provider | plan | final\_plan\_present |
| X04 | 1 | no\_tool | deterministic\_fake\_provider | plan | request\_meals |
| X04 | 1 | no\_tool | deterministic\_fake\_provider | plan | request\_diet |
| X04 | 1 | no\_tool | deterministic\_fake\_provider | plan | request\_budget\_period |
| X04 | 1 | no\_tool | deterministic\_fake\_provider | plan | request\_plan\_cap\_cents |
| X04 | 1 | no\_tool | deterministic\_fake\_provider | plan | request\_pantry\_ingredients |
| X04 | 1 | no\_tool | deterministic\_fake\_provider | plan | request\_ingredient\_exclusions |
| X04 | 1 | no\_tool | deterministic\_fake\_provider | plan | expected\_accepted |
| X04 | 1 | no\_tool | deterministic\_fake\_provider | plan | expected\_total\_cents |
| X04 | 1 | no\_tool | deterministic\_fake\_provider | plan | expected\_notice |
| X04 | 1 | no\_tool | deterministic\_fake\_provider | plan | expected\_catalog\_version |
| X04 | 1 | no\_tool | deterministic\_fake\_provider | plan | expected\_budget\_available\_cents |
| X04 | 1 | no\_tool | deterministic\_fake\_provider | plan | budget\_arithmetic |
| X04 | 1 | no\_tool | deterministic\_fake\_provider | plan | budget\_pending |
| X04 | 1 | no\_tool | deterministic\_fake\_provider | plan | budget\_stale |
| X04 | 1 | no\_tool | deterministic\_fake\_provider | plan | golden\_lines |
| X04 | 1 | no\_tool | deterministic\_fake\_provider | plan | integrity\_ingredient\_coverage |
| X04 | 1 | no\_tool | deterministic\_fake\_provider | plan | integrity\_quantities |
| X04 | 1 | no\_tool | deterministic\_fake\_provider | plan | integrity\_package\_rounding |
| X04 | 1 | no\_tool | deterministic\_fake\_provider | plan | integrity\_sample\_costs |
| X04 | 1 | no\_tool | deterministic\_fake\_provider | plan | integrity\_diet |
| X04 | 1 | no\_tool | deterministic\_fake\_provider | plan | integrity\_exclusions |
| X04 | 1 | no\_tool | deterministic\_fake\_provider | plan | integrity\_total\_cents |
| X04 | 1 | no\_tool | deterministic\_fake\_provider | plan | integrity\_acceptance |
| X04 | 1 | no\_tool | deterministic\_fake\_provider | plan | integrity\_budget\_cap |
| X04 | 1 | no\_tool | deterministic\_fake\_provider | plan | integrity\_notice |
| X04 | 1 | no\_tool | deterministic\_fake\_provider | plan | integrity\_catalog\_version |
| X04 | 1 | no\_tool | deterministic\_fake\_provider | plan | integrity\_schema |
| X04 | 2 | no\_tool | deterministic\_fake\_provider | plan | final\_plan\_present |
| X04 | 2 | no\_tool | deterministic\_fake\_provider | plan | request\_meals |
| X04 | 2 | no\_tool | deterministic\_fake\_provider | plan | request\_diet |
| X04 | 2 | no\_tool | deterministic\_fake\_provider | plan | request\_budget\_period |
| X04 | 2 | no\_tool | deterministic\_fake\_provider | plan | request\_plan\_cap\_cents |
| X04 | 2 | no\_tool | deterministic\_fake\_provider | plan | request\_pantry\_ingredients |
| X04 | 2 | no\_tool | deterministic\_fake\_provider | plan | request\_ingredient\_exclusions |
| X04 | 2 | no\_tool | deterministic\_fake\_provider | plan | expected\_accepted |
| X04 | 2 | no\_tool | deterministic\_fake\_provider | plan | expected\_total\_cents |
| X04 | 2 | no\_tool | deterministic\_fake\_provider | plan | expected\_notice |
| X04 | 2 | no\_tool | deterministic\_fake\_provider | plan | expected\_catalog\_version |
| X04 | 2 | no\_tool | deterministic\_fake\_provider | plan | expected\_budget\_available\_cents |
| X04 | 2 | no\_tool | deterministic\_fake\_provider | plan | budget\_arithmetic |
| X04 | 2 | no\_tool | deterministic\_fake\_provider | plan | budget\_pending |
| X04 | 2 | no\_tool | deterministic\_fake\_provider | plan | budget\_stale |
| X04 | 2 | no\_tool | deterministic\_fake\_provider | plan | golden\_lines |
| X04 | 2 | no\_tool | deterministic\_fake\_provider | plan | integrity\_ingredient\_coverage |
| X04 | 2 | no\_tool | deterministic\_fake\_provider | plan | integrity\_quantities |
| X04 | 2 | no\_tool | deterministic\_fake\_provider | plan | integrity\_package\_rounding |
| X04 | 2 | no\_tool | deterministic\_fake\_provider | plan | integrity\_sample\_costs |
| X04 | 2 | no\_tool | deterministic\_fake\_provider | plan | integrity\_diet |
| X04 | 2 | no\_tool | deterministic\_fake\_provider | plan | integrity\_exclusions |
| X04 | 2 | no\_tool | deterministic\_fake\_provider | plan | integrity\_total\_cents |
| X04 | 2 | no\_tool | deterministic\_fake\_provider | plan | integrity\_acceptance |
| X04 | 2 | no\_tool | deterministic\_fake\_provider | plan | integrity\_budget\_cap |
| X04 | 2 | no\_tool | deterministic\_fake\_provider | plan | integrity\_notice |
| X04 | 2 | no\_tool | deterministic\_fake\_provider | plan | integrity\_catalog\_version |
| X04 | 2 | no\_tool | deterministic\_fake\_provider | plan | integrity\_schema |
| X04 | 3 | no\_tool | deterministic\_fake\_provider | plan | final\_plan\_present |
| X04 | 3 | no\_tool | deterministic\_fake\_provider | plan | request\_meals |
| X04 | 3 | no\_tool | deterministic\_fake\_provider | plan | request\_diet |
| X04 | 3 | no\_tool | deterministic\_fake\_provider | plan | request\_budget\_period |
| X04 | 3 | no\_tool | deterministic\_fake\_provider | plan | request\_plan\_cap\_cents |
| X04 | 3 | no\_tool | deterministic\_fake\_provider | plan | request\_pantry\_ingredients |
| X04 | 3 | no\_tool | deterministic\_fake\_provider | plan | request\_ingredient\_exclusions |
| X04 | 3 | no\_tool | deterministic\_fake\_provider | plan | expected\_accepted |
| X04 | 3 | no\_tool | deterministic\_fake\_provider | plan | expected\_total\_cents |
| X04 | 3 | no\_tool | deterministic\_fake\_provider | plan | expected\_notice |
| X04 | 3 | no\_tool | deterministic\_fake\_provider | plan | expected\_catalog\_version |
| X04 | 3 | no\_tool | deterministic\_fake\_provider | plan | expected\_budget\_available\_cents |
| X04 | 3 | no\_tool | deterministic\_fake\_provider | plan | budget\_arithmetic |
| X04 | 3 | no\_tool | deterministic\_fake\_provider | plan | budget\_pending |
| X04 | 3 | no\_tool | deterministic\_fake\_provider | plan | budget\_stale |
| X04 | 3 | no\_tool | deterministic\_fake\_provider | plan | golden\_lines |
| X04 | 3 | no\_tool | deterministic\_fake\_provider | plan | integrity\_ingredient\_coverage |
| X04 | 3 | no\_tool | deterministic\_fake\_provider | plan | integrity\_quantities |
| X04 | 3 | no\_tool | deterministic\_fake\_provider | plan | integrity\_package\_rounding |
| X04 | 3 | no\_tool | deterministic\_fake\_provider | plan | integrity\_sample\_costs |
| X04 | 3 | no\_tool | deterministic\_fake\_provider | plan | integrity\_diet |
| X04 | 3 | no\_tool | deterministic\_fake\_provider | plan | integrity\_exclusions |
| X04 | 3 | no\_tool | deterministic\_fake\_provider | plan | integrity\_total\_cents |
| X04 | 3 | no\_tool | deterministic\_fake\_provider | plan | integrity\_acceptance |
| X04 | 3 | no\_tool | deterministic\_fake\_provider | plan | integrity\_budget\_cap |
| X04 | 3 | no\_tool | deterministic\_fake\_provider | plan | integrity\_notice |
| X04 | 3 | no\_tool | deterministic\_fake\_provider | plan | integrity\_catalog\_version |
| X04 | 3 | no\_tool | deterministic\_fake\_provider | plan | integrity\_schema |
| A01 | 1 | no\_tool | deterministic\_fake\_provider | plan | final\_plan\_present |
| A01 | 1 | no\_tool | deterministic\_fake\_provider | plan | request\_meals |
| A01 | 1 | no\_tool | deterministic\_fake\_provider | plan | request\_diet |
| A01 | 1 | no\_tool | deterministic\_fake\_provider | plan | request\_budget\_period |
| A01 | 1 | no\_tool | deterministic\_fake\_provider | plan | request\_plan\_cap\_cents |
| A01 | 1 | no\_tool | deterministic\_fake\_provider | plan | request\_pantry\_ingredients |
| A01 | 1 | no\_tool | deterministic\_fake\_provider | plan | request\_ingredient\_exclusions |
| A01 | 1 | no\_tool | deterministic\_fake\_provider | plan | expected\_accepted |
| A01 | 1 | no\_tool | deterministic\_fake\_provider | plan | expected\_total\_cents |
| A01 | 1 | no\_tool | deterministic\_fake\_provider | plan | expected\_notice |
| A01 | 1 | no\_tool | deterministic\_fake\_provider | plan | expected\_catalog\_version |
| A01 | 1 | no\_tool | deterministic\_fake\_provider | plan | expected\_budget\_available\_cents |
| A01 | 1 | no\_tool | deterministic\_fake\_provider | plan | budget\_arithmetic |
| A01 | 1 | no\_tool | deterministic\_fake\_provider | plan | budget\_pending |
| A01 | 1 | no\_tool | deterministic\_fake\_provider | plan | budget\_stale |
| A01 | 1 | no\_tool | deterministic\_fake\_provider | plan | integrity\_ingredient\_coverage |
| A01 | 1 | no\_tool | deterministic\_fake\_provider | plan | integrity\_quantities |
| A01 | 1 | no\_tool | deterministic\_fake\_provider | plan | integrity\_package\_rounding |
| A01 | 1 | no\_tool | deterministic\_fake\_provider | plan | integrity\_sample\_costs |
| A01 | 1 | no\_tool | deterministic\_fake\_provider | plan | integrity\_diet |
| A01 | 1 | no\_tool | deterministic\_fake\_provider | plan | integrity\_exclusions |
| A01 | 1 | no\_tool | deterministic\_fake\_provider | plan | integrity\_total\_cents |
| A01 | 1 | no\_tool | deterministic\_fake\_provider | plan | integrity\_acceptance |
| A01 | 1 | no\_tool | deterministic\_fake\_provider | plan | integrity\_budget\_cap |
| A01 | 1 | no\_tool | deterministic\_fake\_provider | plan | integrity\_notice |
| A01 | 1 | no\_tool | deterministic\_fake\_provider | plan | integrity\_catalog\_version |
| A01 | 1 | no\_tool | deterministic\_fake\_provider | plan | integrity\_schema |
| A01 | 2 | no\_tool | deterministic\_fake\_provider | plan | final\_plan\_present |
| A01 | 2 | no\_tool | deterministic\_fake\_provider | plan | request\_meals |
| A01 | 2 | no\_tool | deterministic\_fake\_provider | plan | request\_diet |
| A01 | 2 | no\_tool | deterministic\_fake\_provider | plan | request\_budget\_period |
| A01 | 2 | no\_tool | deterministic\_fake\_provider | plan | request\_plan\_cap\_cents |
| A01 | 2 | no\_tool | deterministic\_fake\_provider | plan | request\_pantry\_ingredients |
| A01 | 2 | no\_tool | deterministic\_fake\_provider | plan | request\_ingredient\_exclusions |
| A01 | 2 | no\_tool | deterministic\_fake\_provider | plan | expected\_accepted |
| A01 | 2 | no\_tool | deterministic\_fake\_provider | plan | expected\_total\_cents |
| A01 | 2 | no\_tool | deterministic\_fake\_provider | plan | expected\_notice |
| A01 | 2 | no\_tool | deterministic\_fake\_provider | plan | expected\_catalog\_version |
| A01 | 2 | no\_tool | deterministic\_fake\_provider | plan | expected\_budget\_available\_cents |
| A01 | 2 | no\_tool | deterministic\_fake\_provider | plan | budget\_arithmetic |
| A01 | 2 | no\_tool | deterministic\_fake\_provider | plan | budget\_pending |
| A01 | 2 | no\_tool | deterministic\_fake\_provider | plan | budget\_stale |
| A01 | 2 | no\_tool | deterministic\_fake\_provider | plan | integrity\_ingredient\_coverage |
| A01 | 2 | no\_tool | deterministic\_fake\_provider | plan | integrity\_quantities |
| A01 | 2 | no\_tool | deterministic\_fake\_provider | plan | integrity\_package\_rounding |
| A01 | 2 | no\_tool | deterministic\_fake\_provider | plan | integrity\_sample\_costs |
| A01 | 2 | no\_tool | deterministic\_fake\_provider | plan | integrity\_diet |
| A01 | 2 | no\_tool | deterministic\_fake\_provider | plan | integrity\_exclusions |
| A01 | 2 | no\_tool | deterministic\_fake\_provider | plan | integrity\_total\_cents |
| A01 | 2 | no\_tool | deterministic\_fake\_provider | plan | integrity\_acceptance |
| A01 | 2 | no\_tool | deterministic\_fake\_provider | plan | integrity\_budget\_cap |
| A01 | 2 | no\_tool | deterministic\_fake\_provider | plan | integrity\_notice |
| A01 | 2 | no\_tool | deterministic\_fake\_provider | plan | integrity\_catalog\_version |
| A01 | 2 | no\_tool | deterministic\_fake\_provider | plan | integrity\_schema |
| A01 | 3 | no\_tool | deterministic\_fake\_provider | plan | final\_plan\_present |
| A01 | 3 | no\_tool | deterministic\_fake\_provider | plan | request\_meals |
| A01 | 3 | no\_tool | deterministic\_fake\_provider | plan | request\_diet |
| A01 | 3 | no\_tool | deterministic\_fake\_provider | plan | request\_budget\_period |
| A01 | 3 | no\_tool | deterministic\_fake\_provider | plan | request\_plan\_cap\_cents |
| A01 | 3 | no\_tool | deterministic\_fake\_provider | plan | request\_pantry\_ingredients |
| A01 | 3 | no\_tool | deterministic\_fake\_provider | plan | request\_ingredient\_exclusions |
| A01 | 3 | no\_tool | deterministic\_fake\_provider | plan | expected\_accepted |
| A01 | 3 | no\_tool | deterministic\_fake\_provider | plan | expected\_total\_cents |
| A01 | 3 | no\_tool | deterministic\_fake\_provider | plan | expected\_notice |
| A01 | 3 | no\_tool | deterministic\_fake\_provider | plan | expected\_catalog\_version |
| A01 | 3 | no\_tool | deterministic\_fake\_provider | plan | expected\_budget\_available\_cents |
| A01 | 3 | no\_tool | deterministic\_fake\_provider | plan | budget\_arithmetic |
| A01 | 3 | no\_tool | deterministic\_fake\_provider | plan | budget\_pending |
| A01 | 3 | no\_tool | deterministic\_fake\_provider | plan | budget\_stale |
| A01 | 3 | no\_tool | deterministic\_fake\_provider | plan | integrity\_ingredient\_coverage |
| A01 | 3 | no\_tool | deterministic\_fake\_provider | plan | integrity\_quantities |
| A01 | 3 | no\_tool | deterministic\_fake\_provider | plan | integrity\_package\_rounding |
| A01 | 3 | no\_tool | deterministic\_fake\_provider | plan | integrity\_sample\_costs |
| A01 | 3 | no\_tool | deterministic\_fake\_provider | plan | integrity\_diet |
| A01 | 3 | no\_tool | deterministic\_fake\_provider | plan | integrity\_exclusions |
| A01 | 3 | no\_tool | deterministic\_fake\_provider | plan | integrity\_total\_cents |
| A01 | 3 | no\_tool | deterministic\_fake\_provider | plan | integrity\_acceptance |
| A01 | 3 | no\_tool | deterministic\_fake\_provider | plan | integrity\_budget\_cap |
| A01 | 3 | no\_tool | deterministic\_fake\_provider | plan | integrity\_notice |
| A01 | 3 | no\_tool | deterministic\_fake\_provider | plan | integrity\_catalog\_version |
| A01 | 3 | no\_tool | deterministic\_fake\_provider | plan | integrity\_schema |
| F01 | 1 | tool\_enabled | deterministic\_fake\_provider | tools | expected\_tool\_selection |
| F01 | 1 | tool\_enabled | deterministic\_fake\_provider | tools | expected\_arguments |
| F01 | 1 | tool\_enabled | deterministic\_fake\_provider | plan | final\_plan\_present |
| F01 | 1 | tool\_enabled | deterministic\_fake\_provider | plan | request\_meals |
| F01 | 1 | tool\_enabled | deterministic\_fake\_provider | plan | request\_diet |
| F01 | 1 | tool\_enabled | deterministic\_fake\_provider | plan | request\_budget\_period |
| F01 | 1 | tool\_enabled | deterministic\_fake\_provider | plan | request\_plan\_cap\_cents |
| F01 | 1 | tool\_enabled | deterministic\_fake\_provider | plan | request\_pantry\_ingredients |
| F01 | 1 | tool\_enabled | deterministic\_fake\_provider | plan | request\_ingredient\_exclusions |
| F01 | 1 | tool\_enabled | deterministic\_fake\_provider | plan | expected\_accepted |
| F01 | 1 | tool\_enabled | deterministic\_fake\_provider | plan | expected\_total\_cents |
| F01 | 1 | tool\_enabled | deterministic\_fake\_provider | plan | expected\_notice |
| F01 | 1 | tool\_enabled | deterministic\_fake\_provider | plan | expected\_catalog\_version |
| F01 | 1 | tool\_enabled | deterministic\_fake\_provider | plan | expected\_budget\_available\_cents |
| F01 | 1 | tool\_enabled | deterministic\_fake\_provider | plan | budget\_arithmetic |
| F01 | 1 | tool\_enabled | deterministic\_fake\_provider | plan | budget\_pending |
| F01 | 1 | tool\_enabled | deterministic\_fake\_provider | plan | budget\_stale |
| F01 | 1 | tool\_enabled | deterministic\_fake\_provider | plan | golden\_lines |
| F01 | 1 | tool\_enabled | deterministic\_fake\_provider | plan | integrity\_ingredient\_coverage |
| F01 | 1 | tool\_enabled | deterministic\_fake\_provider | plan | integrity\_quantities |
| F01 | 1 | tool\_enabled | deterministic\_fake\_provider | plan | integrity\_package\_rounding |
| F01 | 1 | tool\_enabled | deterministic\_fake\_provider | plan | integrity\_sample\_costs |
| F01 | 1 | tool\_enabled | deterministic\_fake\_provider | plan | integrity\_diet |
| F01 | 1 | tool\_enabled | deterministic\_fake\_provider | plan | integrity\_exclusions |
| F01 | 1 | tool\_enabled | deterministic\_fake\_provider | plan | integrity\_total\_cents |
| F01 | 1 | tool\_enabled | deterministic\_fake\_provider | plan | integrity\_acceptance |
| F01 | 1 | tool\_enabled | deterministic\_fake\_provider | plan | integrity\_budget\_cap |
| F01 | 1 | tool\_enabled | deterministic\_fake\_provider | plan | integrity\_notice |
| F01 | 1 | tool\_enabled | deterministic\_fake\_provider | plan | integrity\_catalog\_version |
| F01 | 1 | tool\_enabled | deterministic\_fake\_provider | plan | integrity\_schema |
| F01 | 2 | tool\_enabled | deterministic\_fake\_provider | tools | expected\_tool\_selection |
| F01 | 2 | tool\_enabled | deterministic\_fake\_provider | tools | expected\_arguments |
| F01 | 2 | tool\_enabled | deterministic\_fake\_provider | plan | final\_plan\_present |
| F01 | 2 | tool\_enabled | deterministic\_fake\_provider | plan | request\_meals |
| F01 | 2 | tool\_enabled | deterministic\_fake\_provider | plan | request\_diet |
| F01 | 2 | tool\_enabled | deterministic\_fake\_provider | plan | request\_budget\_period |
| F01 | 2 | tool\_enabled | deterministic\_fake\_provider | plan | request\_plan\_cap\_cents |
| F01 | 2 | tool\_enabled | deterministic\_fake\_provider | plan | request\_pantry\_ingredients |
| F01 | 2 | tool\_enabled | deterministic\_fake\_provider | plan | request\_ingredient\_exclusions |
| F01 | 2 | tool\_enabled | deterministic\_fake\_provider | plan | expected\_accepted |
| F01 | 2 | tool\_enabled | deterministic\_fake\_provider | plan | expected\_total\_cents |
| F01 | 2 | tool\_enabled | deterministic\_fake\_provider | plan | expected\_notice |
| F01 | 2 | tool\_enabled | deterministic\_fake\_provider | plan | expected\_catalog\_version |
| F01 | 2 | tool\_enabled | deterministic\_fake\_provider | plan | expected\_budget\_available\_cents |
| F01 | 2 | tool\_enabled | deterministic\_fake\_provider | plan | budget\_arithmetic |
| F01 | 2 | tool\_enabled | deterministic\_fake\_provider | plan | budget\_pending |
| F01 | 2 | tool\_enabled | deterministic\_fake\_provider | plan | budget\_stale |
| F01 | 2 | tool\_enabled | deterministic\_fake\_provider | plan | golden\_lines |
| F01 | 2 | tool\_enabled | deterministic\_fake\_provider | plan | integrity\_ingredient\_coverage |
| F01 | 2 | tool\_enabled | deterministic\_fake\_provider | plan | integrity\_quantities |
| F01 | 2 | tool\_enabled | deterministic\_fake\_provider | plan | integrity\_package\_rounding |
| F01 | 2 | tool\_enabled | deterministic\_fake\_provider | plan | integrity\_sample\_costs |
| F01 | 2 | tool\_enabled | deterministic\_fake\_provider | plan | integrity\_diet |
| F01 | 2 | tool\_enabled | deterministic\_fake\_provider | plan | integrity\_exclusions |
| F01 | 2 | tool\_enabled | deterministic\_fake\_provider | plan | integrity\_total\_cents |
| F01 | 2 | tool\_enabled | deterministic\_fake\_provider | plan | integrity\_acceptance |
| F01 | 2 | tool\_enabled | deterministic\_fake\_provider | plan | integrity\_budget\_cap |
| F01 | 2 | tool\_enabled | deterministic\_fake\_provider | plan | integrity\_notice |
| F01 | 2 | tool\_enabled | deterministic\_fake\_provider | plan | integrity\_catalog\_version |
| F01 | 2 | tool\_enabled | deterministic\_fake\_provider | plan | integrity\_schema |
| F01 | 3 | tool\_enabled | deterministic\_fake\_provider | tools | expected\_tool\_selection |
| F01 | 3 | tool\_enabled | deterministic\_fake\_provider | tools | expected\_arguments |
| F01 | 3 | tool\_enabled | deterministic\_fake\_provider | plan | final\_plan\_present |
| F01 | 3 | tool\_enabled | deterministic\_fake\_provider | plan | request\_meals |
| F01 | 3 | tool\_enabled | deterministic\_fake\_provider | plan | request\_diet |
| F01 | 3 | tool\_enabled | deterministic\_fake\_provider | plan | request\_budget\_period |
| F01 | 3 | tool\_enabled | deterministic\_fake\_provider | plan | request\_plan\_cap\_cents |
| F01 | 3 | tool\_enabled | deterministic\_fake\_provider | plan | request\_pantry\_ingredients |
| F01 | 3 | tool\_enabled | deterministic\_fake\_provider | plan | request\_ingredient\_exclusions |
| F01 | 3 | tool\_enabled | deterministic\_fake\_provider | plan | expected\_accepted |
| F01 | 3 | tool\_enabled | deterministic\_fake\_provider | plan | expected\_total\_cents |
| F01 | 3 | tool\_enabled | deterministic\_fake\_provider | plan | expected\_notice |
| F01 | 3 | tool\_enabled | deterministic\_fake\_provider | plan | expected\_catalog\_version |
| F01 | 3 | tool\_enabled | deterministic\_fake\_provider | plan | expected\_budget\_available\_cents |
| F01 | 3 | tool\_enabled | deterministic\_fake\_provider | plan | budget\_arithmetic |
| F01 | 3 | tool\_enabled | deterministic\_fake\_provider | plan | budget\_pending |
| F01 | 3 | tool\_enabled | deterministic\_fake\_provider | plan | budget\_stale |
| F01 | 3 | tool\_enabled | deterministic\_fake\_provider | plan | golden\_lines |
| F01 | 3 | tool\_enabled | deterministic\_fake\_provider | plan | integrity\_ingredient\_coverage |
| F01 | 3 | tool\_enabled | deterministic\_fake\_provider | plan | integrity\_quantities |
| F01 | 3 | tool\_enabled | deterministic\_fake\_provider | plan | integrity\_package\_rounding |
| F01 | 3 | tool\_enabled | deterministic\_fake\_provider | plan | integrity\_sample\_costs |
| F01 | 3 | tool\_enabled | deterministic\_fake\_provider | plan | integrity\_diet |
| F01 | 3 | tool\_enabled | deterministic\_fake\_provider | plan | integrity\_exclusions |
| F01 | 3 | tool\_enabled | deterministic\_fake\_provider | plan | integrity\_total\_cents |
| F01 | 3 | tool\_enabled | deterministic\_fake\_provider | plan | integrity\_acceptance |
| F01 | 3 | tool\_enabled | deterministic\_fake\_provider | plan | integrity\_budget\_cap |
| F01 | 3 | tool\_enabled | deterministic\_fake\_provider | plan | integrity\_notice |
| F01 | 3 | tool\_enabled | deterministic\_fake\_provider | plan | integrity\_catalog\_version |
| F01 | 3 | tool\_enabled | deterministic\_fake\_provider | plan | integrity\_schema |
| F02 | 1 | tool\_enabled | deterministic\_fake\_provider | tools | expected\_tool\_selection |
| F02 | 1 | tool\_enabled | deterministic\_fake\_provider | tools | expected\_arguments |
| F02 | 1 | tool\_enabled | deterministic\_fake\_provider | plan | final\_plan\_present |
| F02 | 1 | tool\_enabled | deterministic\_fake\_provider | plan | request\_meals |
| F02 | 1 | tool\_enabled | deterministic\_fake\_provider | plan | request\_diet |
| F02 | 1 | tool\_enabled | deterministic\_fake\_provider | plan | request\_budget\_period |
| F02 | 1 | tool\_enabled | deterministic\_fake\_provider | plan | request\_plan\_cap\_cents |
| F02 | 1 | tool\_enabled | deterministic\_fake\_provider | plan | request\_pantry\_ingredients |
| F02 | 1 | tool\_enabled | deterministic\_fake\_provider | plan | request\_ingredient\_exclusions |
| F02 | 1 | tool\_enabled | deterministic\_fake\_provider | plan | expected\_accepted |
| F02 | 1 | tool\_enabled | deterministic\_fake\_provider | plan | expected\_total\_cents |
| F02 | 1 | tool\_enabled | deterministic\_fake\_provider | plan | expected\_notice |
| F02 | 1 | tool\_enabled | deterministic\_fake\_provider | plan | expected\_catalog\_version |
| F02 | 1 | tool\_enabled | deterministic\_fake\_provider | plan | expected\_budget\_available\_cents |
| F02 | 1 | tool\_enabled | deterministic\_fake\_provider | plan | budget\_arithmetic |
| F02 | 1 | tool\_enabled | deterministic\_fake\_provider | plan | budget\_pending |
| F02 | 1 | tool\_enabled | deterministic\_fake\_provider | plan | budget\_stale |
| F02 | 1 | tool\_enabled | deterministic\_fake\_provider | plan | golden\_lines |
| F02 | 1 | tool\_enabled | deterministic\_fake\_provider | plan | integrity\_ingredient\_coverage |
| F02 | 1 | tool\_enabled | deterministic\_fake\_provider | plan | integrity\_quantities |
| F02 | 1 | tool\_enabled | deterministic\_fake\_provider | plan | integrity\_package\_rounding |
| F02 | 1 | tool\_enabled | deterministic\_fake\_provider | plan | integrity\_sample\_costs |
| F02 | 1 | tool\_enabled | deterministic\_fake\_provider | plan | integrity\_diet |
| F02 | 1 | tool\_enabled | deterministic\_fake\_provider | plan | integrity\_exclusions |
| F02 | 1 | tool\_enabled | deterministic\_fake\_provider | plan | integrity\_total\_cents |
| F02 | 1 | tool\_enabled | deterministic\_fake\_provider | plan | integrity\_acceptance |
| F02 | 1 | tool\_enabled | deterministic\_fake\_provider | plan | integrity\_budget\_cap |
| F02 | 1 | tool\_enabled | deterministic\_fake\_provider | plan | integrity\_notice |
| F02 | 1 | tool\_enabled | deterministic\_fake\_provider | plan | integrity\_catalog\_version |
| F02 | 1 | tool\_enabled | deterministic\_fake\_provider | plan | integrity\_schema |
| F02 | 2 | tool\_enabled | deterministic\_fake\_provider | tools | expected\_tool\_selection |
| F02 | 2 | tool\_enabled | deterministic\_fake\_provider | tools | expected\_arguments |
| F02 | 2 | tool\_enabled | deterministic\_fake\_provider | plan | final\_plan\_present |
| F02 | 2 | tool\_enabled | deterministic\_fake\_provider | plan | request\_meals |
| F02 | 2 | tool\_enabled | deterministic\_fake\_provider | plan | request\_diet |
| F02 | 2 | tool\_enabled | deterministic\_fake\_provider | plan | request\_budget\_period |
| F02 | 2 | tool\_enabled | deterministic\_fake\_provider | plan | request\_plan\_cap\_cents |
| F02 | 2 | tool\_enabled | deterministic\_fake\_provider | plan | request\_pantry\_ingredients |
| F02 | 2 | tool\_enabled | deterministic\_fake\_provider | plan | request\_ingredient\_exclusions |
| F02 | 2 | tool\_enabled | deterministic\_fake\_provider | plan | expected\_accepted |
| F02 | 2 | tool\_enabled | deterministic\_fake\_provider | plan | expected\_total\_cents |
| F02 | 2 | tool\_enabled | deterministic\_fake\_provider | plan | expected\_notice |
| F02 | 2 | tool\_enabled | deterministic\_fake\_provider | plan | expected\_catalog\_version |
| F02 | 2 | tool\_enabled | deterministic\_fake\_provider | plan | expected\_budget\_available\_cents |
| F02 | 2 | tool\_enabled | deterministic\_fake\_provider | plan | budget\_arithmetic |
| F02 | 2 | tool\_enabled | deterministic\_fake\_provider | plan | budget\_pending |
| F02 | 2 | tool\_enabled | deterministic\_fake\_provider | plan | budget\_stale |
| F02 | 2 | tool\_enabled | deterministic\_fake\_provider | plan | golden\_lines |
| F02 | 2 | tool\_enabled | deterministic\_fake\_provider | plan | integrity\_ingredient\_coverage |
| F02 | 2 | tool\_enabled | deterministic\_fake\_provider | plan | integrity\_quantities |
| F02 | 2 | tool\_enabled | deterministic\_fake\_provider | plan | integrity\_package\_rounding |
| F02 | 2 | tool\_enabled | deterministic\_fake\_provider | plan | integrity\_sample\_costs |
| F02 | 2 | tool\_enabled | deterministic\_fake\_provider | plan | integrity\_diet |
| F02 | 2 | tool\_enabled | deterministic\_fake\_provider | plan | integrity\_exclusions |
| F02 | 2 | tool\_enabled | deterministic\_fake\_provider | plan | integrity\_total\_cents |
| F02 | 2 | tool\_enabled | deterministic\_fake\_provider | plan | integrity\_acceptance |
| F02 | 2 | tool\_enabled | deterministic\_fake\_provider | plan | integrity\_budget\_cap |
| F02 | 2 | tool\_enabled | deterministic\_fake\_provider | plan | integrity\_notice |
| F02 | 2 | tool\_enabled | deterministic\_fake\_provider | plan | integrity\_catalog\_version |
| F02 | 2 | tool\_enabled | deterministic\_fake\_provider | plan | integrity\_schema |
| F02 | 3 | tool\_enabled | deterministic\_fake\_provider | tools | expected\_tool\_selection |
| F02 | 3 | tool\_enabled | deterministic\_fake\_provider | tools | expected\_arguments |
| F02 | 3 | tool\_enabled | deterministic\_fake\_provider | plan | final\_plan\_present |
| F02 | 3 | tool\_enabled | deterministic\_fake\_provider | plan | request\_meals |
| F02 | 3 | tool\_enabled | deterministic\_fake\_provider | plan | request\_diet |
| F02 | 3 | tool\_enabled | deterministic\_fake\_provider | plan | request\_budget\_period |
| F02 | 3 | tool\_enabled | deterministic\_fake\_provider | plan | request\_plan\_cap\_cents |
| F02 | 3 | tool\_enabled | deterministic\_fake\_provider | plan | request\_pantry\_ingredients |
| F02 | 3 | tool\_enabled | deterministic\_fake\_provider | plan | request\_ingredient\_exclusions |
| F02 | 3 | tool\_enabled | deterministic\_fake\_provider | plan | expected\_accepted |
| F02 | 3 | tool\_enabled | deterministic\_fake\_provider | plan | expected\_total\_cents |
| F02 | 3 | tool\_enabled | deterministic\_fake\_provider | plan | expected\_notice |
| F02 | 3 | tool\_enabled | deterministic\_fake\_provider | plan | expected\_catalog\_version |
| F02 | 3 | tool\_enabled | deterministic\_fake\_provider | plan | expected\_budget\_available\_cents |
| F02 | 3 | tool\_enabled | deterministic\_fake\_provider | plan | budget\_arithmetic |
| F02 | 3 | tool\_enabled | deterministic\_fake\_provider | plan | budget\_pending |
| F02 | 3 | tool\_enabled | deterministic\_fake\_provider | plan | budget\_stale |
| F02 | 3 | tool\_enabled | deterministic\_fake\_provider | plan | golden\_lines |
| F02 | 3 | tool\_enabled | deterministic\_fake\_provider | plan | integrity\_ingredient\_coverage |
| F02 | 3 | tool\_enabled | deterministic\_fake\_provider | plan | integrity\_quantities |
| F02 | 3 | tool\_enabled | deterministic\_fake\_provider | plan | integrity\_package\_rounding |
| F02 | 3 | tool\_enabled | deterministic\_fake\_provider | plan | integrity\_sample\_costs |
| F02 | 3 | tool\_enabled | deterministic\_fake\_provider | plan | integrity\_diet |
| F02 | 3 | tool\_enabled | deterministic\_fake\_provider | plan | integrity\_exclusions |
| F02 | 3 | tool\_enabled | deterministic\_fake\_provider | plan | integrity\_total\_cents |
| F02 | 3 | tool\_enabled | deterministic\_fake\_provider | plan | integrity\_acceptance |
| F02 | 3 | tool\_enabled | deterministic\_fake\_provider | plan | integrity\_budget\_cap |
| F02 | 3 | tool\_enabled | deterministic\_fake\_provider | plan | integrity\_notice |
| F02 | 3 | tool\_enabled | deterministic\_fake\_provider | plan | integrity\_catalog\_version |
| F02 | 3 | tool\_enabled | deterministic\_fake\_provider | plan | integrity\_schema |
| F04 | 1 | tool\_enabled | deterministic\_fake\_provider | tools | expected\_tool\_selection |
| F04 | 1 | tool\_enabled | deterministic\_fake\_provider | tools | expected\_arguments |
| F04 | 2 | tool\_enabled | deterministic\_fake\_provider | tools | expected\_tool\_selection |
| F04 | 2 | tool\_enabled | deterministic\_fake\_provider | tools | expected\_arguments |
| F04 | 3 | tool\_enabled | deterministic\_fake\_provider | tools | expected\_tool\_selection |
| F04 | 3 | tool\_enabled | deterministic\_fake\_provider | tools | expected\_arguments |
| F05 | 1 | tool\_enabled | deterministic\_fake\_provider | tools | expected\_tool\_selection |
| F05 | 1 | tool\_enabled | deterministic\_fake\_provider | tools | expected\_arguments |
| F05 | 1 | tool\_enabled | deterministic\_fake\_provider | plan | final\_plan\_present |
| F05 | 1 | tool\_enabled | deterministic\_fake\_provider | plan | request\_meals |
| F05 | 1 | tool\_enabled | deterministic\_fake\_provider | plan | request\_diet |
| F05 | 1 | tool\_enabled | deterministic\_fake\_provider | plan | request\_budget\_period |
| F05 | 1 | tool\_enabled | deterministic\_fake\_provider | plan | request\_plan\_cap\_cents |
| F05 | 1 | tool\_enabled | deterministic\_fake\_provider | plan | request\_pantry\_ingredients |
| F05 | 1 | tool\_enabled | deterministic\_fake\_provider | plan | request\_ingredient\_exclusions |
| F05 | 1 | tool\_enabled | deterministic\_fake\_provider | plan | expected\_accepted |
| F05 | 1 | tool\_enabled | deterministic\_fake\_provider | plan | expected\_total\_cents |
| F05 | 1 | tool\_enabled | deterministic\_fake\_provider | plan | expected\_notice |
| F05 | 1 | tool\_enabled | deterministic\_fake\_provider | plan | expected\_catalog\_version |
| F05 | 1 | tool\_enabled | deterministic\_fake\_provider | plan | budget\_arithmetic |
| F05 | 1 | tool\_enabled | deterministic\_fake\_provider | plan | budget\_pending |
| F05 | 1 | tool\_enabled | deterministic\_fake\_provider | plan | budget\_stale |
| F05 | 1 | tool\_enabled | deterministic\_fake\_provider | plan | golden\_lines |
| F05 | 1 | tool\_enabled | deterministic\_fake\_provider | plan | integrity\_ingredient\_coverage |
| F05 | 1 | tool\_enabled | deterministic\_fake\_provider | plan | integrity\_quantities |
| F05 | 1 | tool\_enabled | deterministic\_fake\_provider | plan | integrity\_package\_rounding |
| F05 | 1 | tool\_enabled | deterministic\_fake\_provider | plan | integrity\_sample\_costs |
| F05 | 1 | tool\_enabled | deterministic\_fake\_provider | plan | integrity\_diet |
| F05 | 1 | tool\_enabled | deterministic\_fake\_provider | plan | integrity\_exclusions |
| F05 | 1 | tool\_enabled | deterministic\_fake\_provider | plan | integrity\_total\_cents |
| F05 | 1 | tool\_enabled | deterministic\_fake\_provider | plan | integrity\_acceptance |
| F05 | 1 | tool\_enabled | deterministic\_fake\_provider | plan | integrity\_budget\_cap |
| F05 | 1 | tool\_enabled | deterministic\_fake\_provider | plan | integrity\_notice |
| F05 | 1 | tool\_enabled | deterministic\_fake\_provider | plan | integrity\_catalog\_version |
| F05 | 1 | tool\_enabled | deterministic\_fake\_provider | plan | integrity\_schema |
| F05 | 2 | tool\_enabled | deterministic\_fake\_provider | tools | expected\_tool\_selection |
| F05 | 2 | tool\_enabled | deterministic\_fake\_provider | tools | expected\_arguments |
| F05 | 2 | tool\_enabled | deterministic\_fake\_provider | plan | final\_plan\_present |
| F05 | 2 | tool\_enabled | deterministic\_fake\_provider | plan | request\_meals |
| F05 | 2 | tool\_enabled | deterministic\_fake\_provider | plan | request\_diet |
| F05 | 2 | tool\_enabled | deterministic\_fake\_provider | plan | request\_budget\_period |
| F05 | 2 | tool\_enabled | deterministic\_fake\_provider | plan | request\_plan\_cap\_cents |
| F05 | 2 | tool\_enabled | deterministic\_fake\_provider | plan | request\_pantry\_ingredients |
| F05 | 2 | tool\_enabled | deterministic\_fake\_provider | plan | request\_ingredient\_exclusions |
| F05 | 2 | tool\_enabled | deterministic\_fake\_provider | plan | expected\_accepted |
| F05 | 2 | tool\_enabled | deterministic\_fake\_provider | plan | expected\_total\_cents |
| F05 | 2 | tool\_enabled | deterministic\_fake\_provider | plan | expected\_notice |
| F05 | 2 | tool\_enabled | deterministic\_fake\_provider | plan | expected\_catalog\_version |
| F05 | 2 | tool\_enabled | deterministic\_fake\_provider | plan | budget\_arithmetic |
| F05 | 2 | tool\_enabled | deterministic\_fake\_provider | plan | budget\_pending |
| F05 | 2 | tool\_enabled | deterministic\_fake\_provider | plan | budget\_stale |
| F05 | 2 | tool\_enabled | deterministic\_fake\_provider | plan | golden\_lines |
| F05 | 2 | tool\_enabled | deterministic\_fake\_provider | plan | integrity\_ingredient\_coverage |
| F05 | 2 | tool\_enabled | deterministic\_fake\_provider | plan | integrity\_quantities |
| F05 | 2 | tool\_enabled | deterministic\_fake\_provider | plan | integrity\_package\_rounding |
| F05 | 2 | tool\_enabled | deterministic\_fake\_provider | plan | integrity\_sample\_costs |
| F05 | 2 | tool\_enabled | deterministic\_fake\_provider | plan | integrity\_diet |
| F05 | 2 | tool\_enabled | deterministic\_fake\_provider | plan | integrity\_exclusions |
| F05 | 2 | tool\_enabled | deterministic\_fake\_provider | plan | integrity\_total\_cents |
| F05 | 2 | tool\_enabled | deterministic\_fake\_provider | plan | integrity\_acceptance |
| F05 | 2 | tool\_enabled | deterministic\_fake\_provider | plan | integrity\_budget\_cap |
| F05 | 2 | tool\_enabled | deterministic\_fake\_provider | plan | integrity\_notice |
| F05 | 2 | tool\_enabled | deterministic\_fake\_provider | plan | integrity\_catalog\_version |
| F05 | 2 | tool\_enabled | deterministic\_fake\_provider | plan | integrity\_schema |
| F05 | 3 | tool\_enabled | deterministic\_fake\_provider | tools | expected\_tool\_selection |
| F05 | 3 | tool\_enabled | deterministic\_fake\_provider | tools | expected\_arguments |
| F05 | 3 | tool\_enabled | deterministic\_fake\_provider | plan | final\_plan\_present |
| F05 | 3 | tool\_enabled | deterministic\_fake\_provider | plan | request\_meals |
| F05 | 3 | tool\_enabled | deterministic\_fake\_provider | plan | request\_diet |
| F05 | 3 | tool\_enabled | deterministic\_fake\_provider | plan | request\_budget\_period |
| F05 | 3 | tool\_enabled | deterministic\_fake\_provider | plan | request\_plan\_cap\_cents |
| F05 | 3 | tool\_enabled | deterministic\_fake\_provider | plan | request\_pantry\_ingredients |
| F05 | 3 | tool\_enabled | deterministic\_fake\_provider | plan | request\_ingredient\_exclusions |
| F05 | 3 | tool\_enabled | deterministic\_fake\_provider | plan | expected\_accepted |
| F05 | 3 | tool\_enabled | deterministic\_fake\_provider | plan | expected\_total\_cents |
| F05 | 3 | tool\_enabled | deterministic\_fake\_provider | plan | expected\_notice |
| F05 | 3 | tool\_enabled | deterministic\_fake\_provider | plan | expected\_catalog\_version |
| F05 | 3 | tool\_enabled | deterministic\_fake\_provider | plan | budget\_arithmetic |
| F05 | 3 | tool\_enabled | deterministic\_fake\_provider | plan | budget\_pending |
| F05 | 3 | tool\_enabled | deterministic\_fake\_provider | plan | budget\_stale |
| F05 | 3 | tool\_enabled | deterministic\_fake\_provider | plan | golden\_lines |
| F05 | 3 | tool\_enabled | deterministic\_fake\_provider | plan | integrity\_ingredient\_coverage |
| F05 | 3 | tool\_enabled | deterministic\_fake\_provider | plan | integrity\_quantities |
| F05 | 3 | tool\_enabled | deterministic\_fake\_provider | plan | integrity\_package\_rounding |
| F05 | 3 | tool\_enabled | deterministic\_fake\_provider | plan | integrity\_sample\_costs |
| F05 | 3 | tool\_enabled | deterministic\_fake\_provider | plan | integrity\_diet |
| F05 | 3 | tool\_enabled | deterministic\_fake\_provider | plan | integrity\_exclusions |
| F05 | 3 | tool\_enabled | deterministic\_fake\_provider | plan | integrity\_total\_cents |
| F05 | 3 | tool\_enabled | deterministic\_fake\_provider | plan | integrity\_acceptance |
| F05 | 3 | tool\_enabled | deterministic\_fake\_provider | plan | integrity\_budget\_cap |
| F05 | 3 | tool\_enabled | deterministic\_fake\_provider | plan | integrity\_notice |
| F05 | 3 | tool\_enabled | deterministic\_fake\_provider | plan | integrity\_catalog\_version |
| F05 | 3 | tool\_enabled | deterministic\_fake\_provider | plan | integrity\_schema |
| X03 | 1 | tool\_enabled | deterministic\_fake\_provider | outcome | allowed\_outcome |
| X03 | 2 | tool\_enabled | deterministic\_fake\_provider | outcome | allowed\_outcome |
| X03 | 3 | tool\_enabled | deterministic\_fake\_provider | outcome | allowed\_outcome |
| X04 | 1 | tool\_enabled | deterministic\_fake\_provider | tools | expected\_tool\_selection |
| X04 | 1 | tool\_enabled | deterministic\_fake\_provider | tools | expected\_arguments |
| X04 | 1 | tool\_enabled | deterministic\_fake\_provider | plan | final\_plan\_present |
| X04 | 1 | tool\_enabled | deterministic\_fake\_provider | plan | request\_meals |
| X04 | 1 | tool\_enabled | deterministic\_fake\_provider | plan | request\_diet |
| X04 | 1 | tool\_enabled | deterministic\_fake\_provider | plan | request\_budget\_period |
| X04 | 1 | tool\_enabled | deterministic\_fake\_provider | plan | request\_plan\_cap\_cents |
| X04 | 1 | tool\_enabled | deterministic\_fake\_provider | plan | request\_pantry\_ingredients |
| X04 | 1 | tool\_enabled | deterministic\_fake\_provider | plan | request\_ingredient\_exclusions |
| X04 | 1 | tool\_enabled | deterministic\_fake\_provider | plan | expected\_accepted |
| X04 | 1 | tool\_enabled | deterministic\_fake\_provider | plan | expected\_total\_cents |
| X04 | 1 | tool\_enabled | deterministic\_fake\_provider | plan | expected\_notice |
| X04 | 1 | tool\_enabled | deterministic\_fake\_provider | plan | expected\_catalog\_version |
| X04 | 1 | tool\_enabled | deterministic\_fake\_provider | plan | expected\_budget\_available\_cents |
| X04 | 1 | tool\_enabled | deterministic\_fake\_provider | plan | budget\_arithmetic |
| X04 | 1 | tool\_enabled | deterministic\_fake\_provider | plan | budget\_pending |
| X04 | 1 | tool\_enabled | deterministic\_fake\_provider | plan | budget\_stale |
| X04 | 1 | tool\_enabled | deterministic\_fake\_provider | plan | golden\_lines |
| X04 | 1 | tool\_enabled | deterministic\_fake\_provider | plan | integrity\_ingredient\_coverage |
| X04 | 1 | tool\_enabled | deterministic\_fake\_provider | plan | integrity\_quantities |
| X04 | 1 | tool\_enabled | deterministic\_fake\_provider | plan | integrity\_package\_rounding |
| X04 | 1 | tool\_enabled | deterministic\_fake\_provider | plan | integrity\_sample\_costs |
| X04 | 1 | tool\_enabled | deterministic\_fake\_provider | plan | integrity\_diet |
| X04 | 1 | tool\_enabled | deterministic\_fake\_provider | plan | integrity\_exclusions |
| X04 | 1 | tool\_enabled | deterministic\_fake\_provider | plan | integrity\_total\_cents |
| X04 | 1 | tool\_enabled | deterministic\_fake\_provider | plan | integrity\_acceptance |
| X04 | 1 | tool\_enabled | deterministic\_fake\_provider | plan | integrity\_budget\_cap |
| X04 | 1 | tool\_enabled | deterministic\_fake\_provider | plan | integrity\_notice |
| X04 | 1 | tool\_enabled | deterministic\_fake\_provider | plan | integrity\_catalog\_version |
| X04 | 1 | tool\_enabled | deterministic\_fake\_provider | plan | integrity\_schema |
| X04 | 2 | tool\_enabled | deterministic\_fake\_provider | tools | expected\_tool\_selection |
| X04 | 2 | tool\_enabled | deterministic\_fake\_provider | tools | expected\_arguments |
| X04 | 2 | tool\_enabled | deterministic\_fake\_provider | plan | final\_plan\_present |
| X04 | 2 | tool\_enabled | deterministic\_fake\_provider | plan | request\_meals |
| X04 | 2 | tool\_enabled | deterministic\_fake\_provider | plan | request\_diet |
| X04 | 2 | tool\_enabled | deterministic\_fake\_provider | plan | request\_budget\_period |
| X04 | 2 | tool\_enabled | deterministic\_fake\_provider | plan | request\_plan\_cap\_cents |
| X04 | 2 | tool\_enabled | deterministic\_fake\_provider | plan | request\_pantry\_ingredients |
| X04 | 2 | tool\_enabled | deterministic\_fake\_provider | plan | request\_ingredient\_exclusions |
| X04 | 2 | tool\_enabled | deterministic\_fake\_provider | plan | expected\_accepted |
| X04 | 2 | tool\_enabled | deterministic\_fake\_provider | plan | expected\_total\_cents |
| X04 | 2 | tool\_enabled | deterministic\_fake\_provider | plan | expected\_notice |
| X04 | 2 | tool\_enabled | deterministic\_fake\_provider | plan | expected\_catalog\_version |
| X04 | 2 | tool\_enabled | deterministic\_fake\_provider | plan | expected\_budget\_available\_cents |
| X04 | 2 | tool\_enabled | deterministic\_fake\_provider | plan | budget\_arithmetic |
| X04 | 2 | tool\_enabled | deterministic\_fake\_provider | plan | budget\_pending |
| X04 | 2 | tool\_enabled | deterministic\_fake\_provider | plan | budget\_stale |
| X04 | 2 | tool\_enabled | deterministic\_fake\_provider | plan | golden\_lines |
| X04 | 2 | tool\_enabled | deterministic\_fake\_provider | plan | integrity\_ingredient\_coverage |
| X04 | 2 | tool\_enabled | deterministic\_fake\_provider | plan | integrity\_quantities |
| X04 | 2 | tool\_enabled | deterministic\_fake\_provider | plan | integrity\_package\_rounding |
| X04 | 2 | tool\_enabled | deterministic\_fake\_provider | plan | integrity\_sample\_costs |
| X04 | 2 | tool\_enabled | deterministic\_fake\_provider | plan | integrity\_diet |
| X04 | 2 | tool\_enabled | deterministic\_fake\_provider | plan | integrity\_exclusions |
| X04 | 2 | tool\_enabled | deterministic\_fake\_provider | plan | integrity\_total\_cents |
| X04 | 2 | tool\_enabled | deterministic\_fake\_provider | plan | integrity\_acceptance |
| X04 | 2 | tool\_enabled | deterministic\_fake\_provider | plan | integrity\_budget\_cap |
| X04 | 2 | tool\_enabled | deterministic\_fake\_provider | plan | integrity\_notice |
| X04 | 2 | tool\_enabled | deterministic\_fake\_provider | plan | integrity\_catalog\_version |
| X04 | 2 | tool\_enabled | deterministic\_fake\_provider | plan | integrity\_schema |
| X04 | 3 | tool\_enabled | deterministic\_fake\_provider | tools | expected\_tool\_selection |
| X04 | 3 | tool\_enabled | deterministic\_fake\_provider | tools | expected\_arguments |
| X04 | 3 | tool\_enabled | deterministic\_fake\_provider | plan | final\_plan\_present |
| X04 | 3 | tool\_enabled | deterministic\_fake\_provider | plan | request\_meals |
| X04 | 3 | tool\_enabled | deterministic\_fake\_provider | plan | request\_diet |
| X04 | 3 | tool\_enabled | deterministic\_fake\_provider | plan | request\_budget\_period |
| X04 | 3 | tool\_enabled | deterministic\_fake\_provider | plan | request\_plan\_cap\_cents |
| X04 | 3 | tool\_enabled | deterministic\_fake\_provider | plan | request\_pantry\_ingredients |
| X04 | 3 | tool\_enabled | deterministic\_fake\_provider | plan | request\_ingredient\_exclusions |
| X04 | 3 | tool\_enabled | deterministic\_fake\_provider | plan | expected\_accepted |
| X04 | 3 | tool\_enabled | deterministic\_fake\_provider | plan | expected\_total\_cents |
| X04 | 3 | tool\_enabled | deterministic\_fake\_provider | plan | expected\_notice |
| X04 | 3 | tool\_enabled | deterministic\_fake\_provider | plan | expected\_catalog\_version |
| X04 | 3 | tool\_enabled | deterministic\_fake\_provider | plan | expected\_budget\_available\_cents |
| X04 | 3 | tool\_enabled | deterministic\_fake\_provider | plan | budget\_arithmetic |
| X04 | 3 | tool\_enabled | deterministic\_fake\_provider | plan | budget\_pending |
| X04 | 3 | tool\_enabled | deterministic\_fake\_provider | plan | budget\_stale |
| X04 | 3 | tool\_enabled | deterministic\_fake\_provider | plan | golden\_lines |
| X04 | 3 | tool\_enabled | deterministic\_fake\_provider | plan | integrity\_ingredient\_coverage |
| X04 | 3 | tool\_enabled | deterministic\_fake\_provider | plan | integrity\_quantities |
| X04 | 3 | tool\_enabled | deterministic\_fake\_provider | plan | integrity\_package\_rounding |
| X04 | 3 | tool\_enabled | deterministic\_fake\_provider | plan | integrity\_sample\_costs |
| X04 | 3 | tool\_enabled | deterministic\_fake\_provider | plan | integrity\_diet |
| X04 | 3 | tool\_enabled | deterministic\_fake\_provider | plan | integrity\_exclusions |
| X04 | 3 | tool\_enabled | deterministic\_fake\_provider | plan | integrity\_total\_cents |
| X04 | 3 | tool\_enabled | deterministic\_fake\_provider | plan | integrity\_acceptance |
| X04 | 3 | tool\_enabled | deterministic\_fake\_provider | plan | integrity\_budget\_cap |
| X04 | 3 | tool\_enabled | deterministic\_fake\_provider | plan | integrity\_notice |
| X04 | 3 | tool\_enabled | deterministic\_fake\_provider | plan | integrity\_catalog\_version |
| X04 | 3 | tool\_enabled | deterministic\_fake\_provider | plan | integrity\_schema |
| A01 | 1 | tool\_enabled | deterministic\_fake\_provider | tools | expected\_tool\_selection |
| A01 | 1 | tool\_enabled | deterministic\_fake\_provider | tools | expected\_arguments |
| A01 | 1 | tool\_enabled | deterministic\_fake\_provider | plan | final\_plan\_present |
| A01 | 1 | tool\_enabled | deterministic\_fake\_provider | plan | request\_meals |
| A01 | 1 | tool\_enabled | deterministic\_fake\_provider | plan | request\_diet |
| A01 | 1 | tool\_enabled | deterministic\_fake\_provider | plan | request\_budget\_period |
| A01 | 1 | tool\_enabled | deterministic\_fake\_provider | plan | request\_plan\_cap\_cents |
| A01 | 1 | tool\_enabled | deterministic\_fake\_provider | plan | request\_pantry\_ingredients |
| A01 | 1 | tool\_enabled | deterministic\_fake\_provider | plan | request\_ingredient\_exclusions |
| A01 | 1 | tool\_enabled | deterministic\_fake\_provider | plan | expected\_accepted |
| A01 | 1 | tool\_enabled | deterministic\_fake\_provider | plan | expected\_total\_cents |
| A01 | 1 | tool\_enabled | deterministic\_fake\_provider | plan | expected\_notice |
| A01 | 1 | tool\_enabled | deterministic\_fake\_provider | plan | expected\_catalog\_version |
| A01 | 1 | tool\_enabled | deterministic\_fake\_provider | plan | expected\_budget\_available\_cents |
| A01 | 1 | tool\_enabled | deterministic\_fake\_provider | plan | budget\_arithmetic |
| A01 | 1 | tool\_enabled | deterministic\_fake\_provider | plan | budget\_pending |
| A01 | 1 | tool\_enabled | deterministic\_fake\_provider | plan | budget\_stale |
| A01 | 1 | tool\_enabled | deterministic\_fake\_provider | plan | integrity\_ingredient\_coverage |
| A01 | 1 | tool\_enabled | deterministic\_fake\_provider | plan | integrity\_quantities |
| A01 | 1 | tool\_enabled | deterministic\_fake\_provider | plan | integrity\_package\_rounding |
| A01 | 1 | tool\_enabled | deterministic\_fake\_provider | plan | integrity\_sample\_costs |
| A01 | 1 | tool\_enabled | deterministic\_fake\_provider | plan | integrity\_diet |
| A01 | 1 | tool\_enabled | deterministic\_fake\_provider | plan | integrity\_exclusions |
| A01 | 1 | tool\_enabled | deterministic\_fake\_provider | plan | integrity\_total\_cents |
| A01 | 1 | tool\_enabled | deterministic\_fake\_provider | plan | integrity\_acceptance |
| A01 | 1 | tool\_enabled | deterministic\_fake\_provider | plan | integrity\_budget\_cap |
| A01 | 1 | tool\_enabled | deterministic\_fake\_provider | plan | integrity\_notice |
| A01 | 1 | tool\_enabled | deterministic\_fake\_provider | plan | integrity\_catalog\_version |
| A01 | 1 | tool\_enabled | deterministic\_fake\_provider | plan | integrity\_schema |
| A01 | 2 | tool\_enabled | deterministic\_fake\_provider | tools | expected\_tool\_selection |
| A01 | 2 | tool\_enabled | deterministic\_fake\_provider | tools | expected\_arguments |
| A01 | 2 | tool\_enabled | deterministic\_fake\_provider | plan | final\_plan\_present |
| A01 | 2 | tool\_enabled | deterministic\_fake\_provider | plan | request\_meals |
| A01 | 2 | tool\_enabled | deterministic\_fake\_provider | plan | request\_diet |
| A01 | 2 | tool\_enabled | deterministic\_fake\_provider | plan | request\_budget\_period |
| A01 | 2 | tool\_enabled | deterministic\_fake\_provider | plan | request\_plan\_cap\_cents |
| A01 | 2 | tool\_enabled | deterministic\_fake\_provider | plan | request\_pantry\_ingredients |
| A01 | 2 | tool\_enabled | deterministic\_fake\_provider | plan | request\_ingredient\_exclusions |
| A01 | 2 | tool\_enabled | deterministic\_fake\_provider | plan | expected\_accepted |
| A01 | 2 | tool\_enabled | deterministic\_fake\_provider | plan | expected\_total\_cents |
| A01 | 2 | tool\_enabled | deterministic\_fake\_provider | plan | expected\_notice |
| A01 | 2 | tool\_enabled | deterministic\_fake\_provider | plan | expected\_catalog\_version |
| A01 | 2 | tool\_enabled | deterministic\_fake\_provider | plan | expected\_budget\_available\_cents |
| A01 | 2 | tool\_enabled | deterministic\_fake\_provider | plan | budget\_arithmetic |
| A01 | 2 | tool\_enabled | deterministic\_fake\_provider | plan | budget\_pending |
| A01 | 2 | tool\_enabled | deterministic\_fake\_provider | plan | budget\_stale |
| A01 | 2 | tool\_enabled | deterministic\_fake\_provider | plan | integrity\_ingredient\_coverage |
| A01 | 2 | tool\_enabled | deterministic\_fake\_provider | plan | integrity\_quantities |
| A01 | 2 | tool\_enabled | deterministic\_fake\_provider | plan | integrity\_package\_rounding |
| A01 | 2 | tool\_enabled | deterministic\_fake\_provider | plan | integrity\_sample\_costs |
| A01 | 2 | tool\_enabled | deterministic\_fake\_provider | plan | integrity\_diet |
| A01 | 2 | tool\_enabled | deterministic\_fake\_provider | plan | integrity\_exclusions |
| A01 | 2 | tool\_enabled | deterministic\_fake\_provider | plan | integrity\_total\_cents |
| A01 | 2 | tool\_enabled | deterministic\_fake\_provider | plan | integrity\_acceptance |
| A01 | 2 | tool\_enabled | deterministic\_fake\_provider | plan | integrity\_budget\_cap |
| A01 | 2 | tool\_enabled | deterministic\_fake\_provider | plan | integrity\_notice |
| A01 | 2 | tool\_enabled | deterministic\_fake\_provider | plan | integrity\_catalog\_version |
| A01 | 2 | tool\_enabled | deterministic\_fake\_provider | plan | integrity\_schema |
| A01 | 3 | tool\_enabled | deterministic\_fake\_provider | tools | expected\_tool\_selection |
| A01 | 3 | tool\_enabled | deterministic\_fake\_provider | tools | expected\_arguments |
| A01 | 3 | tool\_enabled | deterministic\_fake\_provider | plan | final\_plan\_present |
| A01 | 3 | tool\_enabled | deterministic\_fake\_provider | plan | request\_meals |
| A01 | 3 | tool\_enabled | deterministic\_fake\_provider | plan | request\_diet |
| A01 | 3 | tool\_enabled | deterministic\_fake\_provider | plan | request\_budget\_period |
| A01 | 3 | tool\_enabled | deterministic\_fake\_provider | plan | request\_plan\_cap\_cents |
| A01 | 3 | tool\_enabled | deterministic\_fake\_provider | plan | request\_pantry\_ingredients |
| A01 | 3 | tool\_enabled | deterministic\_fake\_provider | plan | request\_ingredient\_exclusions |
| A01 | 3 | tool\_enabled | deterministic\_fake\_provider | plan | expected\_accepted |
| A01 | 3 | tool\_enabled | deterministic\_fake\_provider | plan | expected\_total\_cents |
| A01 | 3 | tool\_enabled | deterministic\_fake\_provider | plan | expected\_notice |
| A01 | 3 | tool\_enabled | deterministic\_fake\_provider | plan | expected\_catalog\_version |
| A01 | 3 | tool\_enabled | deterministic\_fake\_provider | plan | expected\_budget\_available\_cents |
| A01 | 3 | tool\_enabled | deterministic\_fake\_provider | plan | budget\_arithmetic |
| A01 | 3 | tool\_enabled | deterministic\_fake\_provider | plan | budget\_pending |
| A01 | 3 | tool\_enabled | deterministic\_fake\_provider | plan | budget\_stale |
| A01 | 3 | tool\_enabled | deterministic\_fake\_provider | plan | integrity\_ingredient\_coverage |
| A01 | 3 | tool\_enabled | deterministic\_fake\_provider | plan | integrity\_quantities |
| A01 | 3 | tool\_enabled | deterministic\_fake\_provider | plan | integrity\_package\_rounding |
| A01 | 3 | tool\_enabled | deterministic\_fake\_provider | plan | integrity\_sample\_costs |
| A01 | 3 | tool\_enabled | deterministic\_fake\_provider | plan | integrity\_diet |
| A01 | 3 | tool\_enabled | deterministic\_fake\_provider | plan | integrity\_exclusions |
| A01 | 3 | tool\_enabled | deterministic\_fake\_provider | plan | integrity\_total\_cents |
| A01 | 3 | tool\_enabled | deterministic\_fake\_provider | plan | integrity\_acceptance |
| A01 | 3 | tool\_enabled | deterministic\_fake\_provider | plan | integrity\_budget\_cap |
| A01 | 3 | tool\_enabled | deterministic\_fake\_provider | plan | integrity\_notice |
| A01 | 3 | tool\_enabled | deterministic\_fake\_provider | plan | integrity\_catalog\_version |
| A01 | 3 | tool\_enabled | deterministic\_fake\_provider | plan | integrity\_schema |
| A02 | 1 | tool\_enabled | deterministic\_fake\_provider | tools | expected\_tool\_selection |
| A02 | 1 | tool\_enabled | deterministic\_fake\_provider | tools | expected\_arguments |
| A02 | 1 | tool\_enabled | deterministic\_fake\_provider | outcome | allowed\_outcome |
| A02 | 2 | tool\_enabled | deterministic\_fake\_provider | tools | expected\_tool\_selection |
| A02 | 2 | tool\_enabled | deterministic\_fake\_provider | tools | expected\_arguments |
| A02 | 2 | tool\_enabled | deterministic\_fake\_provider | outcome | allowed\_outcome |
| A02 | 3 | tool\_enabled | deterministic\_fake\_provider | tools | expected\_tool\_selection |
| A02 | 3 | tool\_enabled | deterministic\_fake\_provider | tools | expected\_arguments |
| A02 | 3 | tool\_enabled | deterministic\_fake\_provider | outcome | allowed\_outcome |
| A03 | 1 | tool\_enabled | deterministic\_fake\_provider | outcome | allowed\_outcome |
| A03 | 2 | tool\_enabled | deterministic\_fake\_provider | outcome | allowed\_outcome |
| A03 | 3 | tool\_enabled | deterministic\_fake\_provider | outcome | allowed\_outcome |
| A04 | 1 | tool\_enabled | deterministic\_fake\_provider | outcome | allowed\_outcome |
| A04 | 2 | tool\_enabled | deterministic\_fake\_provider | outcome | allowed\_outcome |
| A04 | 3 | tool\_enabled | deterministic\_fake\_provider | outcome | allowed\_outcome |

## Assessment and execution issues

| Case | Repeat | Condition | Evidence | Quality status | Execution status | Reason |
| --- | --- | --- | --- | --- | --- | --- |
| F01 | 1 | tool\_enabled | deterministic\_fake\_provider | failed | completed | assessment\_failed |
| F01 | 2 | tool\_enabled | deterministic\_fake\_provider | failed | completed | assessment\_failed |
| F01 | 3 | tool\_enabled | deterministic\_fake\_provider | failed | completed | assessment\_failed |
| F02 | 1 | tool\_enabled | deterministic\_fake\_provider | failed | completed | assessment\_failed |
| F02 | 2 | tool\_enabled | deterministic\_fake\_provider | failed | completed | assessment\_failed |
| F02 | 3 | tool\_enabled | deterministic\_fake\_provider | failed | completed | assessment\_failed |
| F04 | 1 | tool\_enabled | deterministic\_fake\_provider | failed | completed | assessment\_failed |
| F04 | 2 | tool\_enabled | deterministic\_fake\_provider | failed | completed | assessment\_failed |
| F04 | 3 | tool\_enabled | deterministic\_fake\_provider | failed | completed | assessment\_failed |
| F05 | 1 | tool\_enabled | deterministic\_fake\_provider | failed | completed | assessment\_failed |
| F05 | 2 | tool\_enabled | deterministic\_fake\_provider | failed | completed | assessment\_failed |
| F05 | 3 | tool\_enabled | deterministic\_fake\_provider | failed | completed | assessment\_failed |
| X03 | 1 | tool\_enabled | deterministic\_fake\_provider | failed | completed | assessment\_failed |
| X03 | 2 | tool\_enabled | deterministic\_fake\_provider | failed | completed | assessment\_failed |
| X03 | 3 | tool\_enabled | deterministic\_fake\_provider | failed | completed | assessment\_failed |
| X04 | 1 | tool\_enabled | deterministic\_fake\_provider | failed | completed | assessment\_failed |
| X04 | 2 | tool\_enabled | deterministic\_fake\_provider | failed | completed | assessment\_failed |
| X04 | 3 | tool\_enabled | deterministic\_fake\_provider | failed | completed | assessment\_failed |
| A01 | 1 | tool\_enabled | deterministic\_fake\_provider | failed | completed | assessment\_failed |
| A01 | 2 | tool\_enabled | deterministic\_fake\_provider | failed | completed | assessment\_failed |
| A01 | 3 | tool\_enabled | deterministic\_fake\_provider | failed | completed | assessment\_failed |
| A02 | 1 | tool\_enabled | deterministic\_fake\_provider | failed | completed | assessment\_failed |
| A02 | 2 | tool\_enabled | deterministic\_fake\_provider | failed | completed | assessment\_failed |
| A02 | 3 | tool\_enabled | deterministic\_fake\_provider | failed | completed | assessment\_failed |
| A03 | 1 | tool\_enabled | deterministic\_fake\_provider | failed | completed | assessment\_failed |
| A03 | 2 | tool\_enabled | deterministic\_fake\_provider | failed | completed | assessment\_failed |
| A03 | 3 | tool\_enabled | deterministic\_fake\_provider | failed | completed | assessment\_failed |
| A04 | 1 | tool\_enabled | deterministic\_fake\_provider | failed | completed | assessment\_failed |
| A04 | 2 | tool\_enabled | deterministic\_fake\_provider | failed | completed | assessment\_failed |
| A04 | 3 | tool\_enabled | deterministic\_fake\_provider | failed | completed | assessment\_failed |
| F01 | 1 | no\_tool | deterministic\_fake\_provider | failed | completed | assessment\_failed |
| F01 | 2 | no\_tool | deterministic\_fake\_provider | failed | completed | assessment\_failed |
| F01 | 3 | no\_tool | deterministic\_fake\_provider | failed | completed | assessment\_failed |
| F02 | 1 | no\_tool | deterministic\_fake\_provider | failed | completed | assessment\_failed |
| F02 | 2 | no\_tool | deterministic\_fake\_provider | failed | completed | assessment\_failed |
| F02 | 3 | no\_tool | deterministic\_fake\_provider | failed | completed | assessment\_failed |
| F04 | 1 | no\_tool | deterministic\_fake\_provider | failed | completed | assessment\_failed |
| F04 | 2 | no\_tool | deterministic\_fake\_provider | failed | completed | assessment\_failed |
| F04 | 3 | no\_tool | deterministic\_fake\_provider | failed | completed | assessment\_failed |
| F05 | 1 | no\_tool | deterministic\_fake\_provider | failed | completed | assessment\_failed |
| F05 | 2 | no\_tool | deterministic\_fake\_provider | failed | completed | assessment\_failed |
| F05 | 3 | no\_tool | deterministic\_fake\_provider | failed | completed | assessment\_failed |
| X02 | 1 | no\_tool | deterministic\_fake\_provider | failed | completed | assessment\_failed |
| X02 | 2 | no\_tool | deterministic\_fake\_provider | failed | completed | assessment\_failed |
| X02 | 3 | no\_tool | deterministic\_fake\_provider | failed | completed | assessment\_failed |
| X03 | 1 | no\_tool | deterministic\_fake\_provider | failed | completed | assessment\_failed |
| X03 | 2 | no\_tool | deterministic\_fake\_provider | failed | completed | assessment\_failed |
| X03 | 3 | no\_tool | deterministic\_fake\_provider | failed | completed | assessment\_failed |
| X04 | 1 | no\_tool | deterministic\_fake\_provider | failed | completed | assessment\_failed |
| X04 | 2 | no\_tool | deterministic\_fake\_provider | failed | completed | assessment\_failed |
| X04 | 3 | no\_tool | deterministic\_fake\_provider | failed | completed | assessment\_failed |
| A01 | 1 | no\_tool | deterministic\_fake\_provider | failed | completed | assessment\_failed |
| A01 | 2 | no\_tool | deterministic\_fake\_provider | failed | completed | assessment\_failed |
| A01 | 3 | no\_tool | deterministic\_fake\_provider | failed | completed | assessment\_failed |
| A02 | 1 | no\_tool | deterministic\_fake\_provider | unassessed | completed | required\_evidence\_unavailable |
| A02 | 2 | no\_tool | deterministic\_fake\_provider | unassessed | completed | required\_evidence\_unavailable |
| A02 | 3 | no\_tool | deterministic\_fake\_provider | unassessed | completed | required\_evidence\_unavailable |
| A03 | 1 | no\_tool | deterministic\_fake\_provider | unassessed | completed | required\_evidence\_unavailable |
| A03 | 2 | no\_tool | deterministic\_fake\_provider | unassessed | completed | required\_evidence\_unavailable |
| A03 | 3 | no\_tool | deterministic\_fake\_provider | unassessed | completed | required\_evidence\_unavailable |
| A04 | 1 | no\_tool | deterministic\_fake\_provider | unassessed | completed | required\_evidence\_unavailable |
| A04 | 2 | no\_tool | deterministic\_fake\_provider | unassessed | completed | required\_evidence\_unavailable |
| A04 | 3 | no\_tool | deterministic\_fake\_provider | unassessed | completed | required\_evidence\_unavailable |

## Measured telemetry

| Total slots |
| --- |
| 138 |

| Condition | Evidence |
| --- | --- |
| controlled\_fixture | deterministic\_fake\_provider |

Known input/output token totals are lower bounds.

| Usage metric | Value |
| --- | --- |
| total slots | 12 |
| observed slots | 12 |
| known usage slots | 0 |
| unknown usage slots | 12 |
| known usage turns | 0 |
| unknown usage turns | 0 |
| input tokens | Unknown |
| output tokens | Unknown |
| known input tokens | Unknown |
| known output tokens | Unknown |

Provider-call samples and unknown counts refer to turns.

| Calls | Known lower bound | Samples | Unknown | Unknown slots |
| --- | --- | --- | --- | --- |
| Unknown | Unknown | 0 | 0 | 12 |

Slot latency measures end-to-end seconds.

| p50 \(s\) | p95 \(s\) | Sample slots | Unknown slots | Method |
| --- | --- | --- | --- | --- |
| 0.005991875019390136 | 0.009485290996963158 | 12 | 0 | nearest\-rank |

| Condition | Evidence |
| --- | --- |
| controlled\_fixture | local\_postgresql |

Known input/output token totals are lower bounds.

| Usage metric | Value |
| --- | --- |
| total slots | 3 |
| observed slots | 3 |
| known usage slots | 0 |
| unknown usage slots | 3 |
| known usage turns | 0 |
| unknown usage turns | 0 |
| input tokens | Unknown |
| output tokens | Unknown |
| known input tokens | Unknown |
| known output tokens | Unknown |

Provider-call samples and unknown counts refer to turns.

| Calls | Known lower bound | Samples | Unknown | Unknown slots |
| --- | --- | --- | --- | --- |
| Unknown | Unknown | 0 | 0 | 3 |

Slot latency measures end-to-end seconds.

| p50 \(s\) | p95 \(s\) | Sample slots | Unknown slots | Method |
| --- | --- | --- | --- | --- |
| 0.2362569580145646 | 0.24329716700594872 | 3 | 0 | nearest\-rank |

| Condition | Evidence |
| --- | --- |
| deterministic | deterministic\_fake\_provider |

Known input/output token totals are lower bounds.

| Usage metric | Value |
| --- | --- |
| total slots | 15 |
| observed slots | 15 |
| known usage slots | 0 |
| unknown usage slots | 15 |
| known usage turns | 0 |
| unknown usage turns | 15 |
| input tokens | Unknown |
| output tokens | Unknown |
| known input tokens | Unknown |
| known output tokens | Unknown |

Provider-call samples and unknown counts refer to turns.

| Calls | Known lower bound | Samples | Unknown | Unknown slots |
| --- | --- | --- | --- | --- |
| 0 | 0 | 15 | 0 | 0 |

Slot latency measures end-to-end seconds.

| p50 \(s\) | p95 \(s\) | Sample slots | Unknown slots | Method |
| --- | --- | --- | --- | --- |
| 0.00041391700506210327 | 0.0005515409866347909 | 15 | 0 | nearest\-rank |

| Condition | Evidence |
| --- | --- |
| deterministic\_fixture | deterministic\_fake\_provider |

Known input/output token totals are lower bounds.

| Usage metric | Value |
| --- | --- |
| total slots | 42 |
| observed slots | 42 |
| known usage slots | 0 |
| unknown usage slots | 42 |
| known usage turns | 0 |
| unknown usage turns | 0 |
| input tokens | Unknown |
| output tokens | Unknown |
| known input tokens | Unknown |
| known output tokens | Unknown |

Provider-call samples and unknown counts refer to turns.

| Calls | Known lower bound | Samples | Unknown | Unknown slots |
| --- | --- | --- | --- | --- |
| Unknown | Unknown | 0 | 0 | 42 |

Slot latency measures end-to-end seconds.

| p50 \(s\) | p95 \(s\) | Sample slots | Unknown slots | Method |
| --- | --- | --- | --- | --- |
| 7.887498941272497e-05 | 0.00013899998157285154 | 42 | 0 | nearest\-rank |

| Condition | Evidence |
| --- | --- |
| no\_tool | deterministic\_fake\_provider |

Known input/output token totals are lower bounds.

| Usage metric | Value |
| --- | --- |
| total slots | 33 |
| observed slots | 33 |
| known usage slots | 33 |
| unknown usage slots | 0 |
| known usage turns | 48 |
| unknown usage turns | 0 |
| input tokens | 240 |
| output tokens | 336 |
| known input tokens | 240 |
| known output tokens | 336 |

Provider-call samples and unknown counts refer to turns.

| Calls | Known lower bound | Samples | Unknown | Unknown slots |
| --- | --- | --- | --- | --- |
| 48 | 48 | 48 | 0 | 0 |

Slot latency measures end-to-end seconds.

| p50 \(s\) | p95 \(s\) | Sample slots | Unknown slots | Method |
| --- | --- | --- | --- | --- |
| 0.0025030420219991356 | 0.0051126670150551945 | 33 | 0 | nearest\-rank |

| Condition | Evidence |
| --- | --- |
| tool\_enabled | deterministic\_fake\_provider |

Known input/output token totals are lower bounds.

| Usage metric | Value |
| --- | --- |
| total slots | 33 |
| observed slots | 33 |
| known usage slots | 33 |
| unknown usage slots | 0 |
| known usage turns | 48 |
| unknown usage turns | 0 |
| input tokens | 240 |
| output tokens | 336 |
| known input tokens | 240 |
| known output tokens | 336 |

Provider-call samples and unknown counts refer to turns.

| Calls | Known lower bound | Samples | Unknown | Unknown slots |
| --- | --- | --- | --- | --- |
| 48 | 48 | 48 | 0 | 0 |

Slot latency measures end-to-end seconds.

| p50 \(s\) | p95 \(s\) | Sample slots | Unknown slots | Method |
| --- | --- | --- | --- | --- |
| 0.002541666995966807 | 0.010647209011949599 | 33 | 0 | nearest\-rank |

## Estimated cost

| Cost field | Value |
| --- | --- |
| Status | not\_applicable |
| Estimated USD | Unknown |
| Known usage lower bound \(USD\) | Unknown |
| Model | us\.amazon\.nova\-2\-lite\-v1\:0 |
| Region | us\-east\-1 |
| Currency | USD |

| Condition | Evidence | Cost status | Known lower bound \(USD\) |
| --- | --- | --- | --- |
| controlled\_fixture | deterministic\_fake\_provider | not\_applicable | Unknown |
| controlled\_fixture | local\_postgresql | not\_applicable | Unknown |
| deterministic | deterministic\_fake\_provider | not\_applicable | Unknown |
| deterministic\_fixture | deterministic\_fake\_provider | not\_applicable | Unknown |
| no\_tool | deterministic\_fake\_provider | not\_applicable | Unknown |
| tool\_enabled | deterministic\_fake\_provider | not\_applicable | Unknown |

[Pricing source](https://pricing.us-east-1.amazonaws.com/offers/v1.0/aws/AmazonBedrock/20261003001138/us-east-1/index.json)

| Pricing field | Value |
| --- | --- |
| model\_id | us\.amazon\.nova\-2\-lite\-v1\:0 |
| region | us\-east\-1 |
| currency | USD |
| input\_usd\_per\_1000 | 0\.0003300000 |
| output\_usd\_per\_1000 | 0\.0027500000 |
| source\_version | 20261003001138 |
| published\_at | 2026\-10\-03T00\:11\:38Z |
| effective\_date | 2026\-10\-01 |
| retrieved\_at | 2026\-10\-03 |

Token-cost estimate in USD. Excludes taxes, other AWS resources, caching discounts, and billing reconciliation. Not an AWS bill. Model billing is not applicable for local/fake evidence; this does not mean a live benchmark is free.
