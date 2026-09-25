import { render, screen } from "@testing-library/react";
import { Badge } from "./Badge";
import type { DomainStatus } from "@/types/domain";

describe("Badge", () => {
  const statuses: DomainStatus[] = ["Draft", "Review", "Published", "Archived"];

  it.each(statuses)("renders %s status text", (status) => {
    render(<Badge status={status} />);
    expect(screen.getByText(status)).toBeInTheDocument();
  });

  it("applies custom className", () => {
    const { container } = render(<Badge status="Draft" className="extra-class" />);
    expect(container.firstChild).toHaveClass("extra-class");
  });

  it("applies status-specific styling", () => {
    const { container: draftContainer } = render(<Badge status="Draft" />);
    const { container: publishedContainer } = render(<Badge status="Published" />);
    const draftEl = draftContainer.firstElementChild;
    const publishedEl = publishedContainer.firstElementChild;
    // Draft and Published should have different classes
    expect(draftEl?.className).not.toBe(publishedEl?.className);
  });
});
