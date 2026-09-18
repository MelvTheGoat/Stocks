import { explainer as bookBuilding } from "./book-building";
import { explainer as dividendYield } from "./dividend-yield";
import { explainer as freeFloat } from "./free-float";
import { explainer as greenshoe } from "./greenshoe";
import { explainer as ipo } from "./ipo";
import { explainer as marketCap } from "./market-cap";
import { explainer as peRatio } from "./pe-ratio";
import { explainer as prospectus } from "./prospectus";
import { explainer as threeStatements } from "./the-three-financial-statements";
import { explainer as whatAShareIs } from "./what-a-share-is";

/**
 * Registry of every explainer. Adding one to the library means adding a file
 * and a line here; nothing else in the application needs to change.
 *
 * Order is the reading order for someone working through the library from the
 * start, which is why it runs from what a share is outward to offer mechanics
 * rather than alphabetically.
 */
export const rawExplainers = [
  whatAShareIs,
  threeStatements,
  marketCap,
  peRatio,
  dividendYield,
  freeFloat,
  prospectus,
  ipo,
  bookBuilding,
  greenshoe,
];
