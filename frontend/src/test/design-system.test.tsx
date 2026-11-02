import { describe, expect, it, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { StatusBadge, InlineAlert, MetricSkeleton, TableSkeleton, Empty } from "@/components/resolve/common";

describe("Design System & Common Components", () => {
  describe("StatusBadge", () => {
    it("renders ticket and incident statuses with appropriate casing and text", () => {
      const { rerender } = render(<StatusBadge status="resolved" />);
      expect(screen.getByText("resolved")).toBeInTheDocument();

      rerender(<StatusBadge status="investigating" />);
      expect(screen.getByText("investigating")).toBeInTheDocument();

      rerender(<StatusBadge status="very_high" />);
      expect(screen.getByText("very high")).toBeInTheDocument();

      rerender(<StatusBadge status="in_progress" size="sm" />);
      expect(screen.getByText("in progress")).toBeInTheDocument();
    });

    it("handles unknown statuses gracefully", () => {
      render(<StatusBadge status="custom_unknown" />);
      expect(screen.getByText("custom unknown")).toBeInTheDocument();
    });
  });

  describe("InlineAlert", () => {
    it("renders alert message and title", () => {
      render(
        <InlineAlert
          type="error"
          title="Submission Failed"
          message="Could not resolve ticket due to network issue."
        />
      );
      expect(screen.getByRole("alert")).toBeInTheDocument();
      expect(screen.getByText("Submission Failed")).toBeInTheDocument();
      expect(screen.getByText("Could not resolve ticket due to network issue.")).toBeInTheDocument();
    });

    it("triggers onDismiss when close button is clicked", () => {
      const handleDismiss = vi.fn();
      render(
        <InlineAlert
          type="success"
          message="Incident confirmed successfully."
          onDismiss={handleDismiss}
        />
      );
      const dismissBtn = screen.getByRole("button", { name: /dismiss alert/i });
      fireEvent.click(dismissBtn);
      expect(handleDismiss).toHaveBeenCalledTimes(1);
    });
  });

  describe("Skeletons & Empty States", () => {
    it("renders MetricSkeleton correctly", () => {
      const { container } = render(<MetricSkeleton />);
      expect(container.querySelector(".animate-pulse")).toBeInTheDocument();
    });

    it("renders TableSkeleton with specified rows and cols", () => {
      const { container } = render(<TableSkeleton rows={3} cols={2} />);
      expect(container.querySelectorAll(".flex.gap-4.items-center").length).toBe(3);
    });

    it("renders Empty state component with title, description, and action button", () => {
      render(
        <Empty
          title="No Tickets Found"
          description="Clear filters to view all customer requests."
          action={<button>Reset Filters</button>}
        />
      );
      expect(screen.getByText("No Tickets Found")).toBeInTheDocument();
      expect(screen.getByText("Clear filters to view all customer requests.")).toBeInTheDocument();
      expect(screen.getByRole("button", { name: "Reset Filters" })).toBeInTheDocument();
    });
  });
});
