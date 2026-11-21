export interface Legalsection {
  title: string;
  content: string;
}

export interface LegalDocument {
  title: string;
  subtitle: string;
  effectiveDate: string;
  sections: Legalsection[];
}

export interface TranslationData {
  meta: {
    code: string;
    name: string;
  };
  buttons: Record<string, string>;
  texts: Record<string, string>;
  seo?: Record<string, Record<string, string>>;
  legal?: Record<string, LegalDocument>;
  qa?: {
    category: Record<
      string,
      {
        title: string;
        content: Record<
          string,
          {
            question: string;
            answer: string;
          }
        >;
      }
    >;
  };
}
