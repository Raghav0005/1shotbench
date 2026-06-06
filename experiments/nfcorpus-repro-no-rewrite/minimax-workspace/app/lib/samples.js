'use strict';

/**
 * Hand-picked NFCorpus sample queries. These come from the official BEIR
 * NFCorpus test topic titles and are useful for the live-search UI. We use a
 * static curated list so the workbench renders a stable set of suggestions
 * even before the TopicsRegistry has been queried.
 */
const SAMPLE_QUERIES = [
  { id: 'PLAIN-12', title: 'Exploiting Autophagy to Live Longer' },
  { id: 'PLAIN-102', title: 'Stopping Heart Disease in Childhood' },
  { id: 'PLAIN-112', title: 'Food Dyes and ADHD' },
  { id: 'PLAIN-123', title: 'How Citrus Might Help Keep Your Hands Warm' },
  { id: 'PLAIN-133', title: 'Starving Tumors of Their Blood Supply' },
  { id: 'PLAIN-175', title: 'Diet and Cellulite' },
  { id: 'PLAIN-186', title: 'Best Treatment for Constipation' },
  { id: 'PLAIN-478', title: 'accidents' },
  { id: 'PLAIN-660', title: 'beans' },
  { id: 'PLAIN-924', title: 'cocaine' },
  { id: 'PLAIN-1018', title: 'DHA' },
  { id: 'PLAIN-2102', title: 'smoking' },
  { id: 'PLAIN-1805', title: "Parkinson's disease" },
  { id: 'PLAIN-2220', title: 'tempeh' },
  { id: 'PLAIN-2354', title: 'walnut oil' },
  { id: 'PLAIN-2430', title: 'Preventing Brain Loss with B Vitamins?' },
  { id: 'PLAIN-2440', title: 'More Than an Apple a Day: Combating Common Diseases' },
  { id: 'PLAIN-2530', title: 'Infectobesity: Adenovirus 36 and Childhood Obesity' },
  { id: 'PLAIN-2820', title: 'Preventing Strokes with Diet' },
  { id: 'PLAIN-3292', title: 'Are Multivitamins Good For You?' },
];

/**
 * Return the first `n` sample queries.
 */
function getSamples(n = 12) {
  return SAMPLE_QUERIES.slice(0, n);
}

module.exports = { SAMPLE_QUERIES, getSamples };
