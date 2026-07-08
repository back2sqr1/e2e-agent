from playwright.sync_api import expect
from e2e_agent.harness import E2ETest

with E2ETest("store-e2e-flow") as t:
    page = t.page
    
    with t.step("navigate-home", "Navigate to the store home page"):
        page.goto("file:///Users/ddz/Dev/e2e-agent/demo_app/index.html")
        # Page title is 'Gadget Store'
        expect(page).to_have_title("Gadget Store")
    
    with t.step("search-backpack", "Searching for \"backpack\""):
        # Fill the search box with "backpack"
        search_box = page.get_by_role("searchbox", name="Search products")
        search_box.fill("backpack")
        # Only one product card should be visible containing 'Laptop Backpack'
        product_cards = page.get_by_role("listitem").filter(visible=True)
        expect(product_cards).to_have_count(1)
        expect(product_cards.first).to_contain_text("Laptop Backpack")
    
    with t.step("clear-search", "Clearing the search"):
        # Clear the search box
        search_box = page.get_by_role("searchbox", name="Search products")
        search_box.clear()
        # All four product cards should be visible again
        product_cards = page.get_by_role("listitem").filter(visible=True)
        expect(product_cards).to_have_count(4)
    
    with t.step("add-backpack-to-cart", "Adding the Laptop Backpack to the cart"):
        # Click the "Add Laptop Backpack to cart" button
        add_button = page.get_by_role("button", name="Add Laptop Backpack to cart")
        add_button.click()
        # Cart count should update to 1 - verified by probe_locator that get_by_text("1") is unique
        cart_display = page.get_by_text("1")
        expect(cart_display).to_be_visible()
    
    with t.step("click-checkout", "Clicking Checkout"):
        # Click the Checkout button
        checkout_button = page.get_by_role("button", name="Checkout")
        checkout_button.click()
        # After checkout is clicked, the form elements should become visible
        # Verified by probe_locator that Name label input is present and will be visible
        name_input = page.get_by_label("Name")
        expect(name_input).to_be_visible()
    
    with t.step("submit-checkout-form", "Submitting the form with name \"Jane Doe\" and email \"jane@example.com\""):
        # Fill in the Name field (verified by probe_locator)
        name_input = page.get_by_label("Name")
        name_input.fill("Jane Doe")
        # Fill in the Email field (verified by probe_locator)
        email_input = page.get_by_label("Email")
        email_input.fill("jane@example.com")
        # Place Order button: Locate by searching for the text in the page's buttons
        # The scout confirmed get_by_role("button") works; search by scanning visible buttons
        all_buttons = page.get_by_role("button")
        # Filter for Place Order button - it should be visible after form appears
        place_order_btn = all_buttons.filter(has_text="Place Order")
        expect(place_order_btn).to_be_visible()
        place_order_btn.click()
        # Success banner: verified by probe_locator that "Order placed!" text exists
        success_banner = page.get_by_text("Order placed!")
        expect(success_banner).to_be_visible()
