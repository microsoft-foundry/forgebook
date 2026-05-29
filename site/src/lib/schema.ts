import { REPO_URL, SITE } from "@/config";
import type { ResolvedAuthor } from "@/lib/registry";

type JsonLdNode = Record<string, unknown>;

interface SchemaContext {
  canonicalUrl: string;
  siteUrl: string;
  socialImageUrl: string;
}

interface TechArticleSchemaContext extends SchemaContext {
  title: string;
  description?: string;
  publishedTime?: string;
  tags: string[];
  authors: ResolvedAuthor[];
  notebookPath: string;
}

const organizationId = "https://microsoft-foundry.github.io/forgebook/#organization";
const websiteId = "https://microsoft-foundry.github.io/forgebook/#website";

function organizationSchema(socialImageUrl: string): JsonLdNode {
  return {
    "@type": "Organization",
    "@id": organizationId,
    name: SITE.formalName,
    url: "https://microsoft-foundry.github.io/forgebook/",
    logo: {
      "@type": "ImageObject",
      url: socialImageUrl,
      width: SITE.socialImage.width,
      height: SITE.socialImage.height,
    },
    sameAs: [REPO_URL, "https://learn.microsoft.com/azure/foundry"],
  };
}

function websiteSchema({ canonicalUrl, siteUrl }: SchemaContext): JsonLdNode {
  return {
    "@type": "WebSite",
    "@id": websiteId,
    name: SITE.name,
    alternateName: SITE.formalName,
    url: siteUrl,
    description: SITE.description,
    inLanguage: "en-US",
    publisher: { "@id": organizationId },
    mainEntityOfPage: canonicalUrl,
  };
}

export function buildHomeSchema(context: SchemaContext): JsonLdNode {
  return {
    "@context": "https://schema.org",
    "@graph": [organizationSchema(context.socialImageUrl), websiteSchema(context)],
  };
}

export function buildTechArticleSchema(context: TechArticleSchemaContext): JsonLdNode {
  const authorNodes = context.authors.map((author) => ({
    "@type": "Person",
    name: author.name,
    url: author.githubUrl,
    sameAs: [author.githubUrl, author.linkedinUrl, author.xUrl].filter(Boolean),
    jobTitle: author.title,
  }));

  return {
    "@context": "https://schema.org",
    "@graph": [
      organizationSchema(context.socialImageUrl),
      websiteSchema(context),
      {
        "@type": "TechArticle",
        "@id": `${context.canonicalUrl}#article`,
        headline: context.title,
        description: context.description,
        url: context.canonicalUrl,
        mainEntityOfPage: context.canonicalUrl,
        image: context.socialImageUrl,
        datePublished: context.publishedTime,
        dateModified: context.publishedTime,
        author: authorNodes,
        publisher: { "@id": organizationId },
        isPartOf: { "@id": websiteId },
        inLanguage: "en-US",
        keywords: context.tags,
        about: context.tags.map((tag) => ({
          "@type": "Thing",
          name: tag,
        })),
        learningResourceType: "Jupyter notebook recipe",
        programmingLanguage: "Python",
        codeRepository: REPO_URL,
        isBasedOn: `${REPO_URL}/blob/main/${context.notebookPath}`,
      },
    ],
  };
}

export function serializeJsonLd(schema: JsonLdNode): string {
  return JSON.stringify(schema).replace(/</g, "\\u003c");
}