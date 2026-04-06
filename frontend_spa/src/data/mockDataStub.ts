// Production stub for lovable/src/data/mockData.ts.
//
// CreateTrip.tsx imports ApplicationQuestion and ApplicationQuestionType from
// @/data/mockData. Both are TypeScript types (erased at runtime), but without
// this alias the real mockData.ts — and its large trip/user fixtures — would
// be included in the production bundle.
//
// In frontend_spa/vite.production.config.ts, "@/data/mockData" is aliased to
// this file, keeping the bundle free of mock data.

export type ApplicationQuestionType = "short" | "long" | "multiple_choice" | "single_select";

export interface ApplicationQuestion {
  id: string;
  question: string;
  type: ApplicationQuestionType;
  required?: boolean;
  options?: string[];
}
