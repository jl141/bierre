/**
 * Terms and Conditions view
 * /terms route.
 */

import { h } from "../lib/dom.js";

/**
 * @param {Object} options
 * @param {{get: function(): Object, set: function(Object): void}} options.store
 * @returns {{mount: function(HTMLElement): void, unmount: function(): void}}
 */
export function createTermsView() {
  let element = null;

  const sections = [
    {
      title: "Intellectual Property",
      blocks: [
        {
          type: "paragraph",
          text: "All content published and made available on our Site is the property of and the Site's creators. This includes, but is not limited to images, text, logos, documents, downloadable files and anything that contributes to the composition of our Site.",
        },
      ],
    },
    {
      title: "Accounts",
      blocks: [
        {
          type: "paragraph",
          text: "When you create an account on our Site, you agree to the following:",
        },
        {
          type: "list",
          items: [
            "You are solely responsible for your account and the security and privacy of your account, including passwords or sensitive information attached to that account; and",
            "All personal information you provide to us through your account is up to date, accurate, and truthful and that you will update your personal information if it changes.",
          ],
        },
        {
          type: "paragraph",
          text: "We reserve the right to suspend or terminate your account if you are using our Site illegally or if you violate these Terms and Conditions.",
        },
      ],
    },
    {
      title: "Links to Other Websites",
      blocks: [
        {
          type: "paragraph",
          text: "Our Site contains links to third party websites or services that we do not own or control. We are not responsible for the content, policies, or practices of any third party website or service linked to on our Site. It is your responsibility to read the terms and conditions and privacy policies of these third party websites before using these sites.",
        },
      ],
    },
    {
      title: "Limitation of Liability",
      blocks: [
        {
          type: "paragraph",
          text: "Bierre and our directors, officers, agents, employees, subsidiaries, and affiliates will not be liable for any actions, claims, losses, damages, liabilities and expenses including legal fees from your use of the Site.",
        },
      ],
    },
    {
      title: "Indemnity",
      blocks: [
        {
          type: "paragraph",
          text: "Except where prohibited by law, by using this Site you indemnify and hold harmless Bierre and our directors, officers, agents, employees, subsidiaries, and affiliates from any actions, claims, losses, damages, liabilities and expenses including legal fees arising out of your use of our Site or your violation of these Terms and Conditions.",
        },
      ],
    },
    {
      title: "Applicable Law",
      blocks: [
        {
          type: "paragraph",
          text: "These Terms and Conditions are governed by the laws of the Province of Manitoba.",
        },
      ],
    },
    {
      title: "Severability",
      blocks: [
        {
          type: "paragraph",
          text: "If at any time any of the provisions set forth in these Terms and Conditions are found to be inconsistent or invalid under applicable laws, those provisions will be deemed void and will be removed from these Terms and Conditions. All other provisions will not be affected by the removal and the rest of these Terms and Conditions will still be considered valid.",
        },
      ],
    },
    {
      title: "Changes",
      blocks: [
        {
          type: "paragraph",
          text: "These Terms and Conditions may be amended from time to time in order to maintain compliance with the law and to reflect any changes to the way we operate our Site and the way we expect users to behave on our Site. We will notify users by email of changes to these Terms and Conditions or post a notice on our Site.",
        },
      ],
    },
    {
      title: "Contact Details",
      blocks: [
        {
          type: "paragraph",
          text: "Please contact us if you have any questions or concerns. Our contact details are as follows:",
        },
        { type: "paragraph", text: "Julian Liu," },
        { type: "email" },
        {
          type: "paragraph",
          text: "You can also contact us at the feedback form available on our Site.",
        },
      ],
    },
    {
      title: "Effective Date",
      blocks: [
        { type: "paragraph", text: "16th Day of September, 2026" },
      ],
    },
  ];

  function renderBlock(block) {
    if (block.type === "list") {
      return h(
        "ol",
        { class: "body" },
        block.items.map((item) => h("li", null, item)),
      );
    }

    if (block.type === "subheading") {
      return h("h3", { class: "panel-subtitle" }, block.text);
    }

    if (block.type === "email") {
      return h(
        "p",
        { class: "body" },
        h("a", { href: "mailto:jul14nl1u@gmail.com" }, "jul14nl1u@gmail.com"),
      );
    }

    return h("p", { class: "body" }, block.text);
  }

  function build() {
    const termsPanel = h(
      "section",
      { class: "panel", id: "terms-panel" },
      h("h1", { class: "panel-title" }, "TERMS AND CONDITIONS"),
      h("p", { class: "body" }, 'These terms and conditions (the "Terms and Conditions") govern the use of Bierre (the "Site"). This Site is owned and operated by Julian Liu. This Site is a scholarly research website.'),
      h("p", { class: "body" }, "By using this Site, you indicate that you have read and understand these Terms and Conditions and agree to abide by them at all times."),
      sections.map((section) =>
        h(
          "section",
          { class: "body-section" },
          h("h2", { class: "panel-title" }, section.title),
          section.blocks.map(renderBlock),
        ),
      ),
    );

    return h("div", { class: "view" }, termsPanel);
  }

  return {
    mount(outlet) {
      if (!element) element = build();
      outlet.append(element);
    },

    unmount() {},
  };
}