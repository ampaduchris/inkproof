# Reasoning audit

Factual claims that the spec relies on, each with its source, how it was checked, and what was not checked. Written by session 1.2 on 19 Nov 2026. A claim here is as good as its source on that date.

## RA-1 National Insurance number format (spec REQ-024, settles N1)

- Claim: a number is two letters, six digits and a final letter A, B, C or D. The first letter of the prefix is not D, F, I, Q, U or V. The second letter is not D, F, I, O, Q, U or V. The prefixes BG, GB, KN, NK, NT, TN and ZZ are not used.
- Source: HM Revenue and Customs, National Insurance manual, NIM39110 "What a NINO looks like", https://www.gov.uk/hmrc-internal-manuals/national-insurance-manual/nim39110. Page read in full on 19 Nov 2026. The page carries no revision date.
- Result: the rules in REQ-024 match the page exactly.
- Also on the page: administrative references such as `OO`, `FY`, `NC` and `PZ` look like numbers but do not use valid prefixes. They are not matched. `PP999999P` has a valid prefix and is documented as not to be used as a number; it still matches the pattern.
- Not checked: whether HMRC has issued every valid prefix, and whether the page has changed since it was read.

## RA-2 German tax identification number (spec REQ-022, REQ-023, section 5.4, settles N2)

- Claims: eleven digits; no leading zero except for test numbers; the eleventh digit is a check digit computed from the first ten; among the first ten digits exactly one digit occurs twice or three times; where a digit occurs three times, the three are not at directly consecutive positions.
- Source: "Prüfung der Steuer- und Steueridentifikationsnummer sowie der Ordnungskriterien bei der Grundsteuer", copyright Bayerisches Landesamt für Steuern, version dated 2 Sep 2026, section 2.2 (pages 6 to 8), https://download.elster.de/download/schnittstellen/Pruefung_der_Steuer_und_Steueridentifikatsnummer.pdf. Text extracted with pypdf 7.1.1 and read on 19 Nov 2026.
- Check digit: the document gives the procedure as code with n = 11 and m = 10. REQ-022 and section 5.4 follow it. All six numbers in the document's example table pass (run on 19 Nov 2026).
- Correction to the draft: the draft's frequency rule lacked the adjacency condition. The document's wording ("niemals an direkt aufeinander folgenden Stellen") is ambiguous. Its own example 65929970489 has the digit 9 at positions 3, 5 and 6, so two equal digits may be adjacent. The reading used is that the three are not all adjacent. All six examples satisfy that reading; one fails the stricter reading "no two adjacent".
- Decision: the frequency filter (REQ-023) stays off in 1.0. A real number satisfies the rule, so the filter can only remove false positives, at the price of missing a mistyped identifier. A missed identifier is worse than an extra redaction.
- Not checked: the legal text behind the document; whether a later version changes the rules; the German ministry's own description.

## RA-3 Fixture values (spec section 10, settles N4)

Values are taken only from examples that their issuers publish.

| Pattern | Values | Source |
| --- | --- | --- |
| `de-tax-id` | 86095742719, 47036892816, 65929970489, 57549285017, 25768131411 (positive); 02476291358 (negative, leading 0) | Example table in the document of RA-2. The document says the five are illustrations from a federal IT centre concept and must not be used in real or test transmissions to the tax authority. inkproof transmits nothing. |
| `uk-ni` | AA123456A, AB123456D, AA111111A (positive) | HMRC Developer Hub, Lifetime ISA API sandbox examples, https://developer.service.hmrc.gov.uk/api-documentation/docs/api/service/lisa-api/2.0/oas/page, read on 19 Nov 2026. |
| `uk-ni` | QQ123456A (negative) | RA-1 source. Its first letter is excluded, so it cannot be issued. |

- Not proved: that any positive value above has never been issued to a person. Published examples make it unlikely, not impossible. Fixtures contain no other identifier-shaped numbers.
- IBAN (International Bank Account Number) canaries and the length table are not covered here (N3, session 1.4).

## RA-4 IBAN country lengths (spec REQ-020, REQ-021, settles N3)

- Claim: the total length of an IBAN is fixed per country by the registry kept by SWIFT as Registration Authority for ISO 13616. Germany and the United Kingdom are 22.
- Source: the IBAN Registry, Release 103, Sep 2026, a 97-page PDF from https://www.swift.com/resource/iban-registry-pdf, saved by the owner as `iban-registry_4.pdf` (SHA-256 `4f352af630187cf9253619d8a46d37edc0e6cecddecfe5dcaa69ac52035f958a`) and supplied on 19 Nov 2026. Text extracted with pypdf 7.1.1. The file is kept in the owner's private folder and is not in this repository. The registry may be newer than release 103 by the time anyone reads this; the data file records the release it was taken from.
- Method: each of the 89 country records gives an "IBAN structure" and an "IBAN length". Both were read for every record.
- Checks run on 19 Nov 2026:
  - For all 89 records the length implied by the structure string equals the stated length.
  - Each record's published example has the stated length and passes the modulo 97 check of REQ-020 (89 of 89).
  - Germany 22 and United Kingdom 22.
  - The lengths agree with two open-source tables for all 89 countries (python-stdnum 2.2, generated from release 101; schwifty 2026.11.3). The same 89 country codes appear in release 103 and in release 101, so no country was added between them. The extra 16 codes in schwifty (AX, BL, GF, GG, GP, IM, JE, MF, MQ, NC, PF, PM, RE, TF, WF, YT) are not registry country records and are not in the table.
- Published examples used as canaries: `DE89370400440532013000` and `GB29NWBK60161331926819`.
- Result: `src/inkproof/data/iban_lengths.json` holds the 89 lengths with the release, source, retrieval date and file hash.
- Not checked: whether a release later than 103 exists; the registry's effective dates for each country; the registry's "IBAN usage" notes, such as countries that restrict use.
