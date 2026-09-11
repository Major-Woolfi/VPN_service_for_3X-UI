export interface LegalSection {
  title: string;
  content: string;
}

export interface LegalDocument {
  title: string;
  subtitle: string;
  effectiveDate: string;
  sections: LegalSection[];
}

export interface TranslationData {
  meta: {
    code: string;
    name: string;
  };
  buttons: Record<string, string>;
  texts: Record<string, string>;
  legal?: Record<string, LegalDocument>;
}
