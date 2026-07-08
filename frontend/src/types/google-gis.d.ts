declare global {
  interface Window {
    google: typeof google;
  }
}

declare namespace google {
  namespace accounts {
    namespace id {
      interface CredentialResponse {
        credential: string;
        select_by?: string;
      }

      interface GsiButtonConfiguration {
        type?: string;
        theme?: 'outline' | 'filled_blue' | 'filled_black';
        size?: 'large' | 'medium' | 'small';
        text?: 'signin_with' | 'signup_with' | 'continue_with' | 'signin';
        shape?: 'rectangular' | 'pill' | 'square' | 'circle';
        logo_alignment?: 'left' | 'center' | 'right';
        width?: string;
        locale?: string;
        click_listener?: () => void;
        itp_support?: boolean;
      }

      type PromptMomentNotification = (
        notificationType: PromptMomentNotificationType,
        skippedReason?: SkippedReason,
      ) => void;

      type PromptMomentNotificationType =
        | 'display'
        | 'skipped'
        | 'not_displayed';

      type SkippedReason =
        | 'user_cancel'
        | 'tap_outside'
        | 'issuing_failed';

      interface IdConfiguration {
        client_id: string;
        auto_select?: boolean;
        callback: (response: CredentialResponse) => void;
        login_uri?: string;
        native_login_uri?: string;
        native_callback?: (response: CredentialResponse) => void;
        cancel_on_tap_outside?: boolean;
        prompt_parent_id?: string;
        nonce?: string;
        context?: 'signin' | 'signup' | 'use';
        ux_mode?: 'popup' | 'redirect';
        allowed_parent_origin?: string | string[];
        intermediate_iframe_close_callback?: () => void;
        itp_check_support?: boolean;
        prompt_parent_id?: string;
        prompt_parent_origin?: string;
      }

      function initialize(config: IdConfiguration): void;
      function renderButton(
        parent: HTMLElement,
        options: GsiButtonConfiguration,
        clickHandler?: () => void
      ): void;
      function prompt(notification?: PromptMomentNotification): void;
      function disableAutoSelect(): void;
    }
  }
}

export {};
