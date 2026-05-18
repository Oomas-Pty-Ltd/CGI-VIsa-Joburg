import React from "react";
import { CheckCircle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useNavigate } from "react-router-dom";

export default function FormReview() {
  const navigate = useNavigate();

  return (
    <div className="min-h-screen bg-gradient-to-br from-orange-50 to-blue-50 p-6 flex items-center justify-center">
      <div className="max-w-2xl w-full glass-card rounded-xl p-12 text-center" data-testid="form-review-container">
        <CheckCircle className="w-24 h-24 text-[#2E8B57] mx-auto mb-6" />
        <h1 className="text-4xl font-bold text-[#1A2E40] mb-4">Application Submitted!</h1>
        <p className="text-lg text-gray-700 mb-8">
          Your consular application has been successfully submitted. You will receive a confirmation email shortly.
        </p>
        <div className="space-y-4">
          <Button
            className="w-full bg-[#E06F2C] hover:bg-[#C55D20] text-white py-6 text-lg"
            data-testid="download-pdf-btn"
          >
            Download Application PDF
          </Button>
          <Button
            variant="outline"
            className="w-full border-[#1A2E40] text-[#1A2E40] hover:bg-[#1A2E40] hover:text-white py-6 text-lg"
            onClick={() => navigate("/consular")}
            data-testid="new-application-btn"
          >
            Start New Application
          </Button>
          <Button
            variant="link"
            onClick={() => navigate("/")}
            className="w-full text-[#1A2E40]"
            data-testid="back-home-btn"
          >
            Back to Home
          </Button>
        </div>
      </div>
    </div>
  );
}