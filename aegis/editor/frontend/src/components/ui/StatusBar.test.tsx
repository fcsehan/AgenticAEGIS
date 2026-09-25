import { render, screen } from "@testing-library/react";
import { StatusBar } from "./StatusBar";

describe("StatusBar", () => {
  it("shows 'Valid' when there are no errors or warnings", () => {
    render(<StatusBar errors={0} warnings={0} />);
    expect(screen.getByText("Valid")).toBeInTheDocument();
  });

  it("shows error count when there are errors", () => {
    render(<StatusBar errors={3} warnings={0} />);
    expect(screen.getByText("3 errors")).toBeInTheDocument();
  });

  it("shows warning count when there are warnings", () => {
    render(<StatusBar errors={0} warnings={2} />);
    expect(screen.getByText("2 warnings")).toBeInTheDocument();
  });

  it("shows both errors and warnings", () => {
    render(<StatusBar errors={1} warnings={1} />);
    expect(screen.getByText("1 error")).toBeInTheDocument();
    expect(screen.getByText("1 warning")).toBeInTheDocument();
  });

  it("uses singular for single error/warning", () => {
    render(<StatusBar errors={1} warnings={1} />);
    expect(screen.getByText("1 error")).toBeInTheDocument();
    expect(screen.getByText("1 warning")).toBeInTheDocument();
  });
});
