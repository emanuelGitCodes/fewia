# Evaluation report

## Coverage

| Coverage | Count |
| --- | --- |
| Primary slots | 90 |
| Baseline slots | 48 |
| Total slots | 138 |
| Scored slots | 138 |
| Unassessed slots | 0 |
| Execution\-failed slots | 31 |

Scored includes passed and failed quality assessments in complete evaluation mode.

## Metadata

| Field | Value |
| --- | --- |
| Mode | complete\_evaluation |
| Revision | 4b877d470258561cedd3375e38efc02362ce5f22 |
| UTC start | 2026\-10\-03T22\:51\:03\.983156\+00\:00 |
| UTC end | 2026\-10\-03T22\:59\:50\.730712\+00\:00 |
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

### no\_tool / real\_bedrock

| Task passed\/applicable | Task passed\/assessed | Failed | Unassessed | Not applicable | Quality scope |
| --- | --- | --- | --- | --- | --- |
| 0\/33 | 0\/33 | 33 | 0 | 0 | language\_task |

| Tool metric | Numerator\/denominator | Unassessed |
| --- | --- | --- |
| Valid calls | 0\/0 \(unassessed\) | 0 |
| Expected tool selection | 0\/0 \(unassessed\) | 0 |
| Expected arguments | 0\/0 \(unassessed\) | 0 |
| Unnecessary calls \(lower is better\) | 0\/0 \(unassessed\) | 0 |

| Public claims supported\/assessed | Public claims supported\/\(assessed\+unknown\) | Unknown | Unsupported | Supported refusals |
| --- | --- | --- | --- | --- |
| 0\/0 \(unassessed\) | 0\/4 | 4 | 0 | 0 |

| Assessment | Passed\/assessed | Unassessed |
| --- | --- | --- |
| Plan | 0\/33 | 0 |
| Outcome | 0\/33 | 0 |
| Fixture | 0\/0 \(unassessed\) | 0 |
| Clarification correctness | 0\/9 | 0 |

### tool\_enabled / real\_bedrock

| Task passed\/applicable | Task passed\/assessed | Failed | Unassessed | Not applicable | Quality scope |
| --- | --- | --- | --- | --- | --- |
| 17\/33 | 17\/33 | 16 | 0 | 0 | language\_task |

| Tool metric | Numerator\/denominator | Unassessed |
| --- | --- | --- |
| Valid calls | 28\/28 | 0 |
| Expected tool selection | 11\/24 | 0 |
| Expected arguments | 11\/24 | 0 |
| Unnecessary calls \(lower is better\) | 2\/13 | 0 |

| Public claims supported\/assessed | Public claims supported\/\(assessed\+unknown\) | Unknown | Unsupported | Supported refusals |
| --- | --- | --- | --- | --- |
| 98\/98 | 98\/100 | 2 | 0 | 10 |

| Assessment | Passed\/assessed | Unassessed |
| --- | --- | --- |
| Plan | 11\/15 | 0 |
| Outcome | 23\/27 | 6 |
| Fixture | 0\/0 \(unassessed\) | 0 |
| Clarification correctness | 6\/7 | 2 |

## Quality failures

| Case | Repeat | Condition | Evidence | Assessment | Failed check |
| --- | --- | --- | --- | --- | --- |
| F01 | 1 | no\_tool | real\_bedrock | plan | observation\_complete |
| F01 | 1 | no\_tool | real\_bedrock | plan | turns\_complete |
| F01 | 1 | no\_tool | real\_bedrock | outcome | Unknown |
| F01 | 2 | no\_tool | real\_bedrock | plan | observation\_complete |
| F01 | 2 | no\_tool | real\_bedrock | plan | turns\_complete |
| F01 | 2 | no\_tool | real\_bedrock | outcome | Unknown |
| F01 | 3 | no\_tool | real\_bedrock | plan | observation\_complete |
| F01 | 3 | no\_tool | real\_bedrock | plan | turns\_complete |
| F01 | 3 | no\_tool | real\_bedrock | outcome | Unknown |
| F02 | 1 | no\_tool | real\_bedrock | plan | observation\_complete |
| F02 | 1 | no\_tool | real\_bedrock | plan | turns\_complete |
| F02 | 1 | no\_tool | real\_bedrock | outcome | Unknown |
| F02 | 2 | no\_tool | real\_bedrock | plan | observation\_complete |
| F02 | 2 | no\_tool | real\_bedrock | plan | turns\_complete |
| F02 | 2 | no\_tool | real\_bedrock | outcome | Unknown |
| F02 | 3 | no\_tool | real\_bedrock | plan | observation\_complete |
| F02 | 3 | no\_tool | real\_bedrock | plan | turns\_complete |
| F02 | 3 | no\_tool | real\_bedrock | outcome | Unknown |
| F04 | 1 | no\_tool | real\_bedrock | plan | observation\_complete |
| F04 | 1 | no\_tool | real\_bedrock | plan | turns\_complete |
| F04 | 1 | no\_tool | real\_bedrock | outcome | Unknown |
| F04 | 2 | no\_tool | real\_bedrock | plan | observation\_complete |
| F04 | 2 | no\_tool | real\_bedrock | plan | turns\_complete |
| F04 | 2 | no\_tool | real\_bedrock | outcome | Unknown |
| F04 | 3 | no\_tool | real\_bedrock | plan | observation\_complete |
| F04 | 3 | no\_tool | real\_bedrock | plan | turns\_complete |
| F04 | 3 | no\_tool | real\_bedrock | outcome | Unknown |
| F05 | 1 | no\_tool | real\_bedrock | plan | observation\_complete |
| F05 | 1 | no\_tool | real\_bedrock | plan | turns\_complete |
| F05 | 1 | no\_tool | real\_bedrock | outcome | Unknown |
| F05 | 2 | no\_tool | real\_bedrock | plan | observation\_complete |
| F05 | 2 | no\_tool | real\_bedrock | plan | turns\_complete |
| F05 | 2 | no\_tool | real\_bedrock | outcome | Unknown |
| F05 | 3 | no\_tool | real\_bedrock | plan | observation\_complete |
| F05 | 3 | no\_tool | real\_bedrock | plan | turns\_complete |
| F05 | 3 | no\_tool | real\_bedrock | outcome | Unknown |
| X02 | 1 | no\_tool | real\_bedrock | plan | observation\_complete |
| X02 | 1 | no\_tool | real\_bedrock | plan | turns\_complete |
| X02 | 1 | no\_tool | real\_bedrock | outcome | Unknown |
| X02 | 2 | no\_tool | real\_bedrock | plan | observation\_complete |
| X02 | 2 | no\_tool | real\_bedrock | plan | turns\_complete |
| X02 | 2 | no\_tool | real\_bedrock | outcome | Unknown |
| X02 | 3 | no\_tool | real\_bedrock | plan | observation\_complete |
| X02 | 3 | no\_tool | real\_bedrock | plan | turns\_complete |
| X02 | 3 | no\_tool | real\_bedrock | outcome | Unknown |
| X03 | 1 | no\_tool | real\_bedrock | plan | observation\_complete |
| X03 | 1 | no\_tool | real\_bedrock | plan | turns\_complete |
| X03 | 1 | no\_tool | real\_bedrock | outcome | Unknown |
| X03 | 2 | no\_tool | real\_bedrock | plan | observation\_complete |
| X03 | 2 | no\_tool | real\_bedrock | plan | turns\_complete |
| X03 | 2 | no\_tool | real\_bedrock | outcome | Unknown |
| X03 | 3 | no\_tool | real\_bedrock | plan | observation\_complete |
| X03 | 3 | no\_tool | real\_bedrock | plan | turns\_complete |
| X03 | 3 | no\_tool | real\_bedrock | outcome | Unknown |
| X04 | 1 | no\_tool | real\_bedrock | plan | observation\_complete |
| X04 | 1 | no\_tool | real\_bedrock | plan | turns\_complete |
| X04 | 1 | no\_tool | real\_bedrock | outcome | Unknown |
| X04 | 2 | no\_tool | real\_bedrock | plan | observation\_complete |
| X04 | 2 | no\_tool | real\_bedrock | plan | turns\_complete |
| X04 | 2 | no\_tool | real\_bedrock | outcome | Unknown |
| X04 | 3 | no\_tool | real\_bedrock | plan | observation\_complete |
| X04 | 3 | no\_tool | real\_bedrock | plan | turns\_complete |
| X04 | 3 | no\_tool | real\_bedrock | outcome | Unknown |
| A01 | 1 | no\_tool | real\_bedrock | plan | observation\_complete |
| A01 | 1 | no\_tool | real\_bedrock | plan | turns\_complete |
| A01 | 1 | no\_tool | real\_bedrock | outcome | Unknown |
| A01 | 2 | no\_tool | real\_bedrock | plan | observation\_complete |
| A01 | 2 | no\_tool | real\_bedrock | plan | turns\_complete |
| A01 | 2 | no\_tool | real\_bedrock | outcome | Unknown |
| A01 | 3 | no\_tool | real\_bedrock | plan | observation\_complete |
| A01 | 3 | no\_tool | real\_bedrock | plan | turns\_complete |
| A01 | 3 | no\_tool | real\_bedrock | outcome | Unknown |
| A02 | 1 | no\_tool | real\_bedrock | plan | observation\_complete |
| A02 | 1 | no\_tool | real\_bedrock | plan | turns\_complete |
| A02 | 1 | no\_tool | real\_bedrock | outcome | Unknown |
| A02 | 2 | no\_tool | real\_bedrock | plan | observation\_complete |
| A02 | 2 | no\_tool | real\_bedrock | plan | turns\_complete |
| A02 | 2 | no\_tool | real\_bedrock | outcome | Unknown |
| A02 | 3 | no\_tool | real\_bedrock | plan | no\_unexpected\_plan |
| A02 | 3 | no\_tool | real\_bedrock | outcome | no\_plan |
| A03 | 1 | no\_tool | real\_bedrock | plan | observation\_complete |
| A03 | 1 | no\_tool | real\_bedrock | plan | turns\_complete |
| A03 | 1 | no\_tool | real\_bedrock | outcome | Unknown |
| A03 | 2 | no\_tool | real\_bedrock | plan | observation\_complete |
| A03 | 2 | no\_tool | real\_bedrock | plan | turns\_complete |
| A03 | 2 | no\_tool | real\_bedrock | outcome | Unknown |
| A03 | 3 | no\_tool | real\_bedrock | plan | observation\_complete |
| A03 | 3 | no\_tool | real\_bedrock | plan | turns\_complete |
| A03 | 3 | no\_tool | real\_bedrock | outcome | Unknown |
| A04 | 1 | no\_tool | real\_bedrock | plan | observation\_complete |
| A04 | 1 | no\_tool | real\_bedrock | plan | turns\_complete |
| A04 | 1 | no\_tool | real\_bedrock | outcome | Unknown |
| A04 | 2 | no\_tool | real\_bedrock | plan | observation\_complete |
| A04 | 2 | no\_tool | real\_bedrock | plan | turns\_complete |
| A04 | 2 | no\_tool | real\_bedrock | outcome | Unknown |
| A04 | 3 | no\_tool | real\_bedrock | plan | observation\_complete |
| A04 | 3 | no\_tool | real\_bedrock | plan | turns\_complete |
| A04 | 3 | no\_tool | real\_bedrock | outcome | Unknown |
| F02 | 1 | tool\_enabled | real\_bedrock | tools | expected\_tool\_selection |
| F02 | 1 | tool\_enabled | real\_bedrock | tools | expected\_arguments |
| F02 | 1 | tool\_enabled | real\_bedrock | plan | final\_plan\_present |
| F02 | 1 | tool\_enabled | real\_bedrock | plan | request\_meals |
| F02 | 1 | tool\_enabled | real\_bedrock | plan | request\_diet |
| F02 | 1 | tool\_enabled | real\_bedrock | plan | request\_budget\_period |
| F02 | 1 | tool\_enabled | real\_bedrock | plan | request\_plan\_cap\_cents |
| F02 | 1 | tool\_enabled | real\_bedrock | plan | request\_pantry\_ingredients |
| F02 | 1 | tool\_enabled | real\_bedrock | plan | request\_ingredient\_exclusions |
| F02 | 1 | tool\_enabled | real\_bedrock | plan | expected\_accepted |
| F02 | 1 | tool\_enabled | real\_bedrock | plan | expected\_total\_cents |
| F02 | 1 | tool\_enabled | real\_bedrock | plan | expected\_notice |
| F02 | 1 | tool\_enabled | real\_bedrock | plan | expected\_catalog\_version |
| F02 | 1 | tool\_enabled | real\_bedrock | plan | expected\_budget\_available\_cents |
| F02 | 1 | tool\_enabled | real\_bedrock | plan | budget\_arithmetic |
| F02 | 1 | tool\_enabled | real\_bedrock | plan | budget\_pending |
| F02 | 1 | tool\_enabled | real\_bedrock | plan | budget\_stale |
| F02 | 1 | tool\_enabled | real\_bedrock | plan | golden\_lines |
| F02 | 1 | tool\_enabled | real\_bedrock | plan | integrity\_ingredient\_coverage |
| F02 | 1 | tool\_enabled | real\_bedrock | plan | integrity\_quantities |
| F02 | 1 | tool\_enabled | real\_bedrock | plan | integrity\_package\_rounding |
| F02 | 1 | tool\_enabled | real\_bedrock | plan | integrity\_sample\_costs |
| F02 | 1 | tool\_enabled | real\_bedrock | plan | integrity\_diet |
| F02 | 1 | tool\_enabled | real\_bedrock | plan | integrity\_exclusions |
| F02 | 1 | tool\_enabled | real\_bedrock | plan | integrity\_total\_cents |
| F02 | 1 | tool\_enabled | real\_bedrock | plan | integrity\_acceptance |
| F02 | 1 | tool\_enabled | real\_bedrock | plan | integrity\_budget\_cap |
| F02 | 1 | tool\_enabled | real\_bedrock | plan | integrity\_notice |
| F02 | 1 | tool\_enabled | real\_bedrock | plan | integrity\_catalog\_version |
| F02 | 1 | tool\_enabled | real\_bedrock | plan | integrity\_schema |
| F02 | 2 | tool\_enabled | real\_bedrock | tools | expected\_tool\_selection |
| F02 | 2 | tool\_enabled | real\_bedrock | tools | expected\_arguments |
| F02 | 2 | tool\_enabled | real\_bedrock | plan | final\_plan\_present |
| F02 | 2 | tool\_enabled | real\_bedrock | plan | request\_meals |
| F02 | 2 | tool\_enabled | real\_bedrock | plan | request\_diet |
| F02 | 2 | tool\_enabled | real\_bedrock | plan | request\_budget\_period |
| F02 | 2 | tool\_enabled | real\_bedrock | plan | request\_plan\_cap\_cents |
| F02 | 2 | tool\_enabled | real\_bedrock | plan | request\_pantry\_ingredients |
| F02 | 2 | tool\_enabled | real\_bedrock | plan | request\_ingredient\_exclusions |
| F02 | 2 | tool\_enabled | real\_bedrock | plan | expected\_accepted |
| F02 | 2 | tool\_enabled | real\_bedrock | plan | expected\_total\_cents |
| F02 | 2 | tool\_enabled | real\_bedrock | plan | expected\_notice |
| F02 | 2 | tool\_enabled | real\_bedrock | plan | expected\_catalog\_version |
| F02 | 2 | tool\_enabled | real\_bedrock | plan | expected\_budget\_available\_cents |
| F02 | 2 | tool\_enabled | real\_bedrock | plan | budget\_arithmetic |
| F02 | 2 | tool\_enabled | real\_bedrock | plan | budget\_pending |
| F02 | 2 | tool\_enabled | real\_bedrock | plan | budget\_stale |
| F02 | 2 | tool\_enabled | real\_bedrock | plan | golden\_lines |
| F02 | 2 | tool\_enabled | real\_bedrock | plan | integrity\_ingredient\_coverage |
| F02 | 2 | tool\_enabled | real\_bedrock | plan | integrity\_quantities |
| F02 | 2 | tool\_enabled | real\_bedrock | plan | integrity\_package\_rounding |
| F02 | 2 | tool\_enabled | real\_bedrock | plan | integrity\_sample\_costs |
| F02 | 2 | tool\_enabled | real\_bedrock | plan | integrity\_diet |
| F02 | 2 | tool\_enabled | real\_bedrock | plan | integrity\_exclusions |
| F02 | 2 | tool\_enabled | real\_bedrock | plan | integrity\_total\_cents |
| F02 | 2 | tool\_enabled | real\_bedrock | plan | integrity\_acceptance |
| F02 | 2 | tool\_enabled | real\_bedrock | plan | integrity\_budget\_cap |
| F02 | 2 | tool\_enabled | real\_bedrock | plan | integrity\_notice |
| F02 | 2 | tool\_enabled | real\_bedrock | plan | integrity\_catalog\_version |
| F02 | 2 | tool\_enabled | real\_bedrock | plan | integrity\_schema |
| F02 | 3 | tool\_enabled | real\_bedrock | tools | expected\_tool\_selection |
| F02 | 3 | tool\_enabled | real\_bedrock | tools | expected\_arguments |
| F02 | 3 | tool\_enabled | real\_bedrock | plan | final\_plan\_present |
| F02 | 3 | tool\_enabled | real\_bedrock | plan | request\_meals |
| F02 | 3 | tool\_enabled | real\_bedrock | plan | request\_diet |
| F02 | 3 | tool\_enabled | real\_bedrock | plan | request\_budget\_period |
| F02 | 3 | tool\_enabled | real\_bedrock | plan | request\_plan\_cap\_cents |
| F02 | 3 | tool\_enabled | real\_bedrock | plan | request\_pantry\_ingredients |
| F02 | 3 | tool\_enabled | real\_bedrock | plan | request\_ingredient\_exclusions |
| F02 | 3 | tool\_enabled | real\_bedrock | plan | expected\_accepted |
| F02 | 3 | tool\_enabled | real\_bedrock | plan | expected\_total\_cents |
| F02 | 3 | tool\_enabled | real\_bedrock | plan | expected\_notice |
| F02 | 3 | tool\_enabled | real\_bedrock | plan | expected\_catalog\_version |
| F02 | 3 | tool\_enabled | real\_bedrock | plan | expected\_budget\_available\_cents |
| F02 | 3 | tool\_enabled | real\_bedrock | plan | budget\_arithmetic |
| F02 | 3 | tool\_enabled | real\_bedrock | plan | budget\_pending |
| F02 | 3 | tool\_enabled | real\_bedrock | plan | budget\_stale |
| F02 | 3 | tool\_enabled | real\_bedrock | plan | golden\_lines |
| F02 | 3 | tool\_enabled | real\_bedrock | plan | integrity\_ingredient\_coverage |
| F02 | 3 | tool\_enabled | real\_bedrock | plan | integrity\_quantities |
| F02 | 3 | tool\_enabled | real\_bedrock | plan | integrity\_package\_rounding |
| F02 | 3 | tool\_enabled | real\_bedrock | plan | integrity\_sample\_costs |
| F02 | 3 | tool\_enabled | real\_bedrock | plan | integrity\_diet |
| F02 | 3 | tool\_enabled | real\_bedrock | plan | integrity\_exclusions |
| F02 | 3 | tool\_enabled | real\_bedrock | plan | integrity\_total\_cents |
| F02 | 3 | tool\_enabled | real\_bedrock | plan | integrity\_acceptance |
| F02 | 3 | tool\_enabled | real\_bedrock | plan | integrity\_budget\_cap |
| F02 | 3 | tool\_enabled | real\_bedrock | plan | integrity\_notice |
| F02 | 3 | tool\_enabled | real\_bedrock | plan | integrity\_catalog\_version |
| F02 | 3 | tool\_enabled | real\_bedrock | plan | integrity\_schema |
| F04 | 1 | tool\_enabled | real\_bedrock | tools | expected\_tool\_selection |
| F04 | 1 | tool\_enabled | real\_bedrock | tools | expected\_arguments |
| F04 | 2 | tool\_enabled | real\_bedrock | tools | expected\_tool\_selection |
| F04 | 2 | tool\_enabled | real\_bedrock | tools | expected\_arguments |
| F04 | 3 | tool\_enabled | real\_bedrock | tools | expected\_tool\_selection |
| F04 | 3 | tool\_enabled | real\_bedrock | tools | expected\_arguments |
| F05 | 1 | tool\_enabled | real\_bedrock | tools | expected\_tool\_selection |
| F05 | 1 | tool\_enabled | real\_bedrock | tools | expected\_arguments |
| F05 | 2 | tool\_enabled | real\_bedrock | tools | expected\_tool\_selection |
| F05 | 2 | tool\_enabled | real\_bedrock | tools | expected\_arguments |
| F05 | 3 | tool\_enabled | real\_bedrock | tools | expected\_tool\_selection |
| F05 | 3 | tool\_enabled | real\_bedrock | tools | expected\_arguments |
| X03 | 1 | tool\_enabled | real\_bedrock | outcome | allowed\_outcome |
| X03 | 2 | tool\_enabled | real\_bedrock | tools | unnecessary\_calls |
| X03 | 3 | tool\_enabled | real\_bedrock | tools | unnecessary\_calls |
| A01 | 1 | tool\_enabled | real\_bedrock | tools | expected\_tool\_selection |
| A01 | 1 | tool\_enabled | real\_bedrock | tools | expected\_arguments |
| A01 | 1 | tool\_enabled | real\_bedrock | plan | final\_plan\_present |
| A01 | 1 | tool\_enabled | real\_bedrock | plan | request\_meals |
| A01 | 1 | tool\_enabled | real\_bedrock | plan | request\_diet |
| A01 | 1 | tool\_enabled | real\_bedrock | plan | request\_budget\_period |
| A01 | 1 | tool\_enabled | real\_bedrock | plan | request\_plan\_cap\_cents |
| A01 | 1 | tool\_enabled | real\_bedrock | plan | request\_pantry\_ingredients |
| A01 | 1 | tool\_enabled | real\_bedrock | plan | request\_ingredient\_exclusions |
| A01 | 1 | tool\_enabled | real\_bedrock | plan | expected\_accepted |
| A01 | 1 | tool\_enabled | real\_bedrock | plan | expected\_total\_cents |
| A01 | 1 | tool\_enabled | real\_bedrock | plan | expected\_notice |
| A01 | 1 | tool\_enabled | real\_bedrock | plan | expected\_catalog\_version |
| A01 | 1 | tool\_enabled | real\_bedrock | plan | expected\_budget\_available\_cents |
| A01 | 1 | tool\_enabled | real\_bedrock | plan | budget\_arithmetic |
| A01 | 1 | tool\_enabled | real\_bedrock | plan | budget\_pending |
| A01 | 1 | tool\_enabled | real\_bedrock | plan | budget\_stale |
| A01 | 1 | tool\_enabled | real\_bedrock | plan | integrity\_ingredient\_coverage |
| A01 | 1 | tool\_enabled | real\_bedrock | plan | integrity\_quantities |
| A01 | 1 | tool\_enabled | real\_bedrock | plan | integrity\_package\_rounding |
| A01 | 1 | tool\_enabled | real\_bedrock | plan | integrity\_sample\_costs |
| A01 | 1 | tool\_enabled | real\_bedrock | plan | integrity\_diet |
| A01 | 1 | tool\_enabled | real\_bedrock | plan | integrity\_exclusions |
| A01 | 1 | tool\_enabled | real\_bedrock | plan | integrity\_total\_cents |
| A01 | 1 | tool\_enabled | real\_bedrock | plan | integrity\_acceptance |
| A01 | 1 | tool\_enabled | real\_bedrock | plan | integrity\_budget\_cap |
| A01 | 1 | tool\_enabled | real\_bedrock | plan | integrity\_notice |
| A01 | 1 | tool\_enabled | real\_bedrock | plan | integrity\_catalog\_version |
| A01 | 1 | tool\_enabled | real\_bedrock | plan | integrity\_schema |
| A02 | 1 | tool\_enabled | real\_bedrock | tools | expected\_tool\_selection |
| A02 | 1 | tool\_enabled | real\_bedrock | tools | expected\_arguments |
| A02 | 1 | tool\_enabled | real\_bedrock | outcome | allowed\_outcome |
| A02 | 2 | tool\_enabled | real\_bedrock | tools | expected\_tool\_selection |
| A02 | 2 | tool\_enabled | real\_bedrock | tools | expected\_arguments |
| A02 | 2 | tool\_enabled | real\_bedrock | outcome | allowed\_outcome |
| A02 | 3 | tool\_enabled | real\_bedrock | tools | expected\_tool\_selection |
| A02 | 3 | tool\_enabled | real\_bedrock | tools | expected\_arguments |
| A02 | 3 | tool\_enabled | real\_bedrock | outcome | allowed\_outcome |

## Assessment and execution issues

| Case | Repeat | Condition | Evidence | Quality status | Execution status | Reason |
| --- | --- | --- | --- | --- | --- | --- |
| F02 | 1 | tool\_enabled | real\_bedrock | failed | completed | assessment\_failed |
| F02 | 2 | tool\_enabled | real\_bedrock | failed | completed | assessment\_failed |
| F02 | 3 | tool\_enabled | real\_bedrock | failed | completed | assessment\_failed |
| F04 | 1 | tool\_enabled | real\_bedrock | failed | completed | assessment\_failed |
| F04 | 2 | tool\_enabled | real\_bedrock | failed | completed | assessment\_failed |
| F04 | 3 | tool\_enabled | real\_bedrock | failed | completed | assessment\_failed |
| F05 | 1 | tool\_enabled | real\_bedrock | failed | completed | assessment\_failed |
| F05 | 2 | tool\_enabled | real\_bedrock | failed | completed | assessment\_failed |
| F05 | 3 | tool\_enabled | real\_bedrock | failed | completed | assessment\_failed |
| X03 | 1 | tool\_enabled | real\_bedrock | failed | completed | assessment\_failed |
| X03 | 2 | tool\_enabled | real\_bedrock | failed | completed | assessment\_failed |
| X03 | 3 | tool\_enabled | real\_bedrock | failed | completed | assessment\_failed |
| A01 | 1 | tool\_enabled | real\_bedrock | failed | completed | assessment\_failed |
| A02 | 1 | tool\_enabled | real\_bedrock | failed | completed | assessment\_failed |
| A02 | 2 | tool\_enabled | real\_bedrock | failed | completed | assessment\_failed |
| A02 | 3 | tool\_enabled | real\_bedrock | failed | completed | assessment\_failed |
| F01 | 1 | no\_tool | real\_bedrock | failed | failed | assessment\_failed |
| F01 | 2 | no\_tool | real\_bedrock | failed | failed | assessment\_failed |
| F01 | 3 | no\_tool | real\_bedrock | failed | failed | assessment\_failed |
| F02 | 1 | no\_tool | real\_bedrock | failed | failed | assessment\_failed |
| F02 | 2 | no\_tool | real\_bedrock | failed | failed | assessment\_failed |
| F02 | 3 | no\_tool | real\_bedrock | failed | failed | assessment\_failed |
| F04 | 1 | no\_tool | real\_bedrock | failed | failed | assessment\_failed |
| F04 | 2 | no\_tool | real\_bedrock | failed | failed | assessment\_failed |
| F04 | 3 | no\_tool | real\_bedrock | failed | failed | assessment\_failed |
| F05 | 1 | no\_tool | real\_bedrock | failed | partial | assessment\_failed |
| F05 | 2 | no\_tool | real\_bedrock | failed | failed | assessment\_failed |
| F05 | 3 | no\_tool | real\_bedrock | failed | failed | assessment\_failed |
| X02 | 1 | no\_tool | real\_bedrock | failed | failed | assessment\_failed |
| X02 | 2 | no\_tool | real\_bedrock | failed | failed | assessment\_failed |
| X02 | 3 | no\_tool | real\_bedrock | failed | failed | assessment\_failed |
| X03 | 1 | no\_tool | real\_bedrock | failed | failed | assessment\_failed |
| X03 | 2 | no\_tool | real\_bedrock | failed | failed | assessment\_failed |
| X03 | 3 | no\_tool | real\_bedrock | failed | failed | assessment\_failed |
| X04 | 1 | no\_tool | real\_bedrock | failed | failed | assessment\_failed |
| X04 | 2 | no\_tool | real\_bedrock | failed | failed | assessment\_failed |
| X04 | 3 | no\_tool | real\_bedrock | failed | failed | assessment\_failed |
| A01 | 1 | no\_tool | real\_bedrock | failed | failed | assessment\_failed |
| A01 | 2 | no\_tool | real\_bedrock | failed | failed | assessment\_failed |
| A01 | 3 | no\_tool | real\_bedrock | failed | failed | assessment\_failed |
| A02 | 1 | no\_tool | real\_bedrock | failed | failed | assessment\_failed |
| A02 | 2 | no\_tool | real\_bedrock | failed | failed | assessment\_failed |
| A02 | 3 | no\_tool | real\_bedrock | failed | completed | assessment\_failed |
| A03 | 1 | no\_tool | real\_bedrock | failed | failed | assessment\_failed |
| A03 | 2 | no\_tool | real\_bedrock | failed | failed | assessment\_failed |
| A03 | 3 | no\_tool | real\_bedrock | failed | failed | assessment\_failed |
| A04 | 1 | no\_tool | real\_bedrock | failed | failed | assessment\_failed |
| A04 | 2 | no\_tool | real\_bedrock | failed | failed | assessment\_failed |
| A04 | 3 | no\_tool | real\_bedrock | failed | failed | assessment\_failed |

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
| 0.006081333005568013 | 0.019690749992150813 | 12 | 0 | nearest\-rank |

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
| 0.20553449998260476 | 0.2239996670105029 | 3 | 0 | nearest\-rank |

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
| 0.0006309999735094607 | 0.0009946250065695494 | 15 | 0 | nearest\-rank |

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
| 9.291601600125432e-05 | 0.00023704097839072347 | 42 | 0 | nearest\-rank |

| Condition | Evidence |
| --- | --- |
| no\_tool | real\_bedrock |

Known input/output token totals are lower bounds.

| Usage metric | Value |
| --- | --- |
| total slots | 33 |
| observed slots | 33 |
| known usage slots | 33 |
| unknown usage slots | 0 |
| known usage turns | 34 |
| unknown usage turns | 0 |
| input tokens | 171948 |
| output tokens | 41817 |
| known input tokens | 171948 |
| known output tokens | 41817 |

Provider-call samples and unknown counts refer to turns.

| Calls | Known lower bound | Samples | Unknown | Unknown slots |
| --- | --- | --- | --- | --- |
| 34 | 34 | 34 | 0 | 0 |

Slot latency measures end-to-end seconds.

| p50 \(s\) | p95 \(s\) | Sample slots | Unknown slots | Method |
| --- | --- | --- | --- | --- |
| 8.033881753974129 | 23.636904094018973 | 33 | 0 | nearest\-rank |

| Condition | Evidence |
| --- | --- |
| tool\_enabled | real\_bedrock |

Known input/output token totals are lower bounds.

| Usage metric | Value |
| --- | --- |
| total slots | 33 |
| observed slots | 33 |
| known usage slots | 33 |
| unknown usage slots | 0 |
| known usage turns | 48 |
| unknown usage turns | 0 |
| input tokens | 189160 |
| output tokens | 36591 |
| known input tokens | 189160 |
| known output tokens | 36591 |

Provider-call samples and unknown counts refer to turns.

| Calls | Known lower bound | Samples | Unknown | Unknown slots |
| --- | --- | --- | --- | --- |
| 76 | 76 | 48 | 0 | 0 |

Slot latency measures end-to-end seconds.

| p50 \(s\) | p95 \(s\) | Sample slots | Unknown slots | Method |
| --- | --- | --- | --- | --- |
| 6.845097460987745 | 12.910748463997152 | 33 | 0 | nearest\-rank |

## Estimated cost

| Cost field | Value |
| --- | --- |
| Status | estimated |
| Estimated USD | 0\.3347876400 |
| Known usage lower bound \(USD\) | 0\.3347876400 |
| Model | us\.amazon\.nova\-2\-lite\-v1\:0 |
| Region | us\-east\-1 |
| Currency | USD |

| Condition | Evidence | Cost status | Known lower bound \(USD\) |
| --- | --- | --- | --- |
| controlled\_fixture | deterministic\_fake\_provider | not\_applicable | Unknown |
| controlled\_fixture | local\_postgresql | not\_applicable | Unknown |
| deterministic | deterministic\_fake\_provider | not\_applicable | Unknown |
| deterministic\_fixture | deterministic\_fake\_provider | not\_applicable | Unknown |
| no\_tool | real\_bedrock | estimated | 0\.1717395900 |
| tool\_enabled | real\_bedrock | estimated | 0\.1630480500 |

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
