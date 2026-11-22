# DA_Sales rehearsal questions

Prepared questions, not yet verified against the natural-language agent runtime.
The underlying semantic model and report are verified. Use the Data Agent UI
after mounting ONT_Business as context; record actual answers and generated queries.

1. What was actual volume by region in October 2026?
2. Which package type had the largest forecast deviation in October 2026 in North?
3. Compare actual and forecast volume by channel for Q3 2026.
4. Compare actual versus forecast for PET 1.0 l in August-October 2026.
5. What was the revenue-weighted margin percentage by channel in October 2026?

Every answer must state its period, region/channel/package filters and units.
Missing forecasts stay missing. Partner delivery records must not multiply sales.

The Act 5 forecast-accuracy question is an additional post-change rehearsal:
the baseline deliberately has no `Forecast Accuracy %` measure. Rehearse that
question after the live measure-addition act rather than claiming baseline support.

Power BI semantic models do not support supplemental data-agent-specific context
in the documented Ontology integration. These questions are retained in the
agent's global instructions; no unsupported semantic-model few-shot payload was
invented. Ontology is context, not a legacy graph/GQL execution source.
